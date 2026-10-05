import streamlit as st
import os, secrets, json, csv, io, hmac, html
from datetime import datetime, timezone
import core
st.set_page_config(page_title='Ayo Menulis Artikel',page_icon='✍️',layout='wide')
def config(k,default=''):
    try: return str(st.secrets.get(k,os.environ.get(k,default)))
    except FileNotFoundError: return os.environ.get(k,default)
core.configure(config('DATABASE_URL'))
try:
    core.init()
except Exception:
    st.error('Database tidak dapat dihubungkan. Periksa DATABASE_URL pada Secrets atau coba lagi nanti. Data tidak dialihkan ke penyimpanan lain.')
    st.stop()
KEY=config('OPENAI_API_KEY'); MODEL=config('OPENAI_MODEL','gpt-4.1-mini'); TEACHER=config('TEACHER_PASSWORD')
st.markdown("""<style>
.stApp {background:linear-gradient(135deg,#fffaf5,#fff1eb);color:#352b30;color-scheme:light}
[data-testid="stSidebar"] {background:#fff4ee;border-right:1px solid #eddad1}
h1,h2,h3 {color:#7b3347}
.block-container {padding-top:2rem;max-width:1200px}
div[data-testid="stMetric"] {background:#fff;padding:1rem;border-radius:16px;border:1px solid #f0ddd3}
[data-testid="stChatMessage"] {background:#fff;border:1px solid #f0ddd3;border-radius:16px}
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button {border-radius:12px}
[data-testid="stSidebar"] [data-testid="stRadio"] label {padding:3px 0}
</style>""",unsafe_allow_html=True)
NAV_ICONS = dict(zip(
    ['Beranda','Akun siswa','Materi pembelajaran','CP kelas XII — Menulis','Tujuan pembelajaran','Contoh teks artikel','Struktur artikel','Kaidah kebahasaan','Latihan / kuis','Evaluasi & refleksi','Umpan balik AI','Tanya jawab AI Tutor','Brainstorming & kerangka','Panduan pemakaian','Dasbor guru'],
    ['🏠','🧑‍🎓','📚','🏆','🎯','📖','🧩','🔤','📝','💭','💬','🤖','💡','🧭','👩‍🏫']))
st.title('✍️ Ayo Menulis Artikel')
st.caption('Dari ide kecil, jadi tulisan yang berarti • Bahasa Indonesia Kelas XII')
if 'user' not in st.session_state: st.session_state.user=None
if 'teacher' not in st.session_state: st.session_state.teacher=False
if 'conversation' not in st.session_state: st.session_state.conversation=secrets.token_hex(12)
if 'attempt' not in st.session_state: st.session_state.attempt=secrets.token_hex(12)
if 'quiz_result' not in st.session_state: st.session_state.quiz_result=None

from remembered_login import device_storage
pending=st.session_state.get('_device_action', {'action':'read','nonce':'read'})
device=device_storage(action=pending['action'],token=pending.get('token',''),nonce=pending['nonce'],key='remember_device')
if isinstance(device,dict) and device.get('nonce')==pending['nonce']:
    if pending['action']!='read':
        st.session_state.pop('_device_action',None)
        st.session_state['_device_token']=device.get('token','')
        if not device.get('available',False):
            st.session_state['_remember_notice']='Browser memblokir penyimpanan. Akun tetap bisa digunakan, tetapi Ingat saya tidak aktif.'
        st.rerun()
    st.session_state['_device_token']=device.get('token','')
    if not st.session_state.user and device.get('token'):
        restored=core.remembered_user(device['token'])
        if restored:
            st.session_state.user=restored
            core.attend(restored['id'])
        else:
            st.session_state['_device_action']={'action':'clear','nonce':secrets.token_hex(8)}
            st.rerun()
if '_remember_notice' in st.session_state:
    st.warning(st.session_state.pop('_remember_notice'))
if not core.persistent():
    st.warning('Mode uji lokal: data di hosting belum permanen. Pengelola perlu mengisi DATABASE_URL sebelum dipakai untuk tugas siswa.')

def set_login(user,remember_me):
    core.forget(st.session_state.get('_device_token',''))
    st.session_state.user=user
    core.attend(user['id'])
    st.session_state['_device_action']={'action':'save' if remember_me else 'clear', 'token':core.remember(user['id']) if remember_me else '', 'nonce':secrets.token_hex(8)}
    st.rerun()

def export(rows,name):
    if not rows: st.info('Belum ada data.'); return
    buf=io.StringIO(); writer=csv.DictWriter(buf,fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        # Lindungi pembukaan CSV pada spreadsheet dari formula yang berasal dari input siswa.
        writer.writerow({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()})
    st.download_button('⬇️ Unduh '+name,('\ufeff'+buf.getvalue()).encode('utf-8'),file_name=name,mime='text/csv')

def identity_required():
    if not st.session_state.user:
        st.info('Masuk atau daftar melalui menu Akun siswa. Materi tetap dapat dibaca tanpa masuk.')
        return False
    return True

with st.sidebar:
    st.header('📚 Ruang belajarmu')
    if st.session_state.user:
        u=st.session_state.user
        st.write(u['name']+' • '+u['class'])
        st.caption(f"Interaksi tersimpan: {core.used(u['id'])} • tanpa batas jumlah")
    st.caption('🟢 AI daring' if KEY else '📖 Tutor lokal terarah')
    menu=st.radio('🧭 Navigasi',[name for name in NAV_ICONS if name not in {'CP kelas XII — Menulis','Tujuan pembelajaran','Contoh teks artikel','Struktur artikel','Kaidah kebahasaan'}],format_func=lambda name: NAV_ICONS[name]+' '+name)
    if st.session_state.user or st.session_state.teacher:
        if st.button('🚪 Keluar akun'):
            core.forget(st.session_state.get('_device_token',''))
            for k in list(st.session_state): del st.session_state[k]
            st.session_state['_device_action']={'action':'clear','nonce':secrets.token_hex(8)}
            st.rerun()

try:
    all_docs=core.docs()
except (FileNotFoundError,UnicodeError,ValueError) as error:
    st.error('Bahan aplikasi belum lengkap atau tidak dapat dibaca. Salin seluruh isi paket lengkap, termasuk folder database, ke folder yang berisi app.py. Pertahankan folder data dan secrets.toml milikmu.')
    st.caption(str(error))
    st.stop()
map_pages={'Materi pembelajaran':['01_materi.txt'],'CP kelas XII — Menulis':['02_cp.txt'],'Tujuan pembelajaran':['03_tujuan.txt'],'Contoh teks artikel':['04_contoh_artikel.txt','04_contoh_pendamping.txt'],'Struktur artikel':['05_struktur.txt'],'Kaidah kebahasaan':['06_kebahasaan.txt']}

if menu=='Beranda':
    st.subheader('🌟 Punya pendapat? Yuk, jadikan artikel!')
    st.write('Pelajari cara merumuskan gagasan, membangun argumen, memeriksa sumber, dan menyunting tulisan. Kamu bisa bertanya pada tutor, berlatih, lalu mengirim artikel untuk dinilai guru.')
    cols=st.columns(3)
    cols[0].metric('📚 Bagian materi','6')
    cols[1].metric('📝 Soal pilihan ganda',len(core.quiz_questions()))
    cols[2].metric('💬 Interaksi per akun','Tanpa batas')
    st.info('Alur belajar: baca CP dan tujuan → pelajari contoh → susun kerangka → kerjakan latihan → tulis artikel → revisi berdasarkan masukan.')
    if st.session_state.user:
        uid=st.session_state.user['id']; p=core.progress(uid)
        st.progress(sum(x['done'] for x in p.values())/len(all_docs),text='Kemajuan materi ditandai oleh siswa')
        st.write('⭐ Favorit:',', '.join(x['topic'] for x in p.values() if x['favorite']) or 'Belum ada')
        qs=core.report('quizzes',uid)
        if qs: st.metric('Nilai kuis tertinggi',max(q['score'] for q in qs))
        core.attend(uid)

elif menu=='Akun siswa':
    if st.session_state.user: st.success('Kamu sudah masuk. Absensi hari ini tersimpan.')
    else:
        login,signup=st.tabs(['🔑 Masuk','🆕 Daftar'])
        with login:
            with st.form('login'):
                username=st.text_input('Username'); password=st.text_input('Kata sandi',type='password')
                remember_me=st.checkbox('Ingat saya selama 30 hari di perangkat ini')
                st.caption('Gunakan hanya pada perangkat pribadi. Keluar akun akan membatalkan akses yang tersimpan.')
                clicked=st.form_submit_button('Masuk')
            if clicked:
                user=core.authenticate(username,password)
                if user:
                    set_login(user,remember_me)
                else: st.error('Username atau kata sandi tidak sesuai.')
        with signup:
            with st.form('signup'):
                username=st.text_input('Buat username'); name=st.text_input('Nama lengkap'); classroom=st.text_input('Kelas',placeholder='XII-1')
                password=st.text_input('Buat kata sandi (minimal 8 karakter)',type='password')
                code=st.text_input('Kode kelas (jika diberikan guru)',type='password')
                remember_signup=st.checkbox('Ingat saya selama 30 hari di perangkat ini',key='remember_signup')
                clicked=st.form_submit_button('Buat akun')
            if clicked:
                try:
                    expected=config('CLASS_CODE')
                    if expected and not hmac.compare_digest(code,expected): raise ValueError('Kode kelas tidak sesuai.')
                    user=core.register(username,name,classroom,password)
                    set_login(user,remember_signup)
                except ValueError as e: st.error(str(e))

elif menu in map_pages:
    material_section=menu
    if menu=='Materi pembelajaran':
        st.subheader('📚 Materi pembelajaran artikel')
        st.caption('Pilih bagian yang ingin dipelajari. CP menunjukkan capaian, tujuan menunjukkan kemampuan yang dilatih, dan bagian lain menjelaskan isi pelajaran.')
        material_section=st.radio('Bagian materi',['CP kelas XII — Menulis','Tujuan pembelajaran','Materi pembelajaran','Contoh teks artikel','Struktur artikel','Kaidah kebahasaan'],index=2,horizontal=True,format_func=lambda name:NAV_ICONS[name]+' '+('Pengertian & pembahasan' if name=='Materi pembelajaran' else name),key='material_section')
    for d in all_docs:
        if d['file'] not in map_pages[material_section]: continue
        st.subheader(NAV_ICONS.get(material_section,'📚')+' '+d['title']); st.markdown(d['text']); st.caption('Asal bahan: '+d['source'])
        if st.session_state.user:
            uid=st.session_state.user['id']; p=core.progress(uid).get(d['title'],{})
            col1,col2=st.columns(2)
            if col1.button('⭐ Hapus favorit' if p.get('favorite') else '☆ Favoritkan',key='fav-'+d['file']):
                core.mark(uid,d['title'],'favorite',not p.get('favorite')); st.rerun()
            if col2.button('↩️ Tandai belum selesai' if p.get('done') else '✅ Tandai selesai',key='done-'+d['file']):
                core.mark(uid,d['title'],'done',not p.get('done')); st.rerun()
    if material_section=='Contoh teks artikel':
        st.subheader('🎨 Tandai peran gagasan')
        st.caption('Pilih paragraf dari contoh utama. Penandaan ini latihan interpretasi, bukan hasil deteksi otomatis.')
        text=next(d['text'] for d in all_docs if d['file']=='04_contoh_artikel.txt')
        article=text.split('Sumber pengembangan gagasan:')[0]
        paragraphs=[p for p in article.split('\n\n') if p.strip()][2:]
        palette={'Gagasan utama':'#dbeafe','Argumentasi':'#dcfce7','Informasi / contoh pendukung':'#fef9c3','Simpulan':'#fee2e2'}
        choice=st.selectbox('Paragraf',range(len(paragraphs)),format_func=lambda i:f'Paragraf {i+1}')
        label=st.selectbox('Peran bagian yang kamu pilih',list(palette))
        if paragraphs: st.markdown(f'<div style="background:{palette[label]};padding:16px;border-radius:10px;color:#172554">{html.escape(paragraphs[choice])}</div>',unsafe_allow_html=True)
        st.write('Diskusikan: kalimat mana yang mendukung pilihanmu? Apakah informasi tersebut sudah disertai sumber yang dapat diperiksa?')

elif menu=='Tanya jawab AI Tutor':
    st.subheader('🤖 Tanya, gali, lalu pahami')
    if identity_required():
        uid=st.session_state.user['id']
        if not KEY: st.info('Tanpa API, tutor memakai jawaban terarah yang disiapkan dari bahan belajar. AI daring diperlukan untuk pertanyaan terbuka dan penalaran yang lebih luas.')
        topic=st.selectbox('Fokus materi',['Semua materi']+[d['title'] for d in all_docs]) if KEY else 'Semua materi'
        rows=core.report('messages',uid)
        conversations=list(dict.fromkeys(r['conversation'] for r in rows if not r['conversation'].startswith(('feedback-','brainstorm-'))))
        if st.session_state.conversation not in conversations: conversations.append(st.session_state.conversation)
        selected=st.selectbox('Percakapan',conversations,index=conversations.index(st.session_state.conversation),format_func=lambda x:'Percakapan '+str(conversations.index(x)+1))
        st.session_state.conversation=selected
        if st.button('➕ Percakapan baru'):
            st.session_state.conversation=secrets.token_hex(12); st.rerun()
        past=core.history(uid,selected)
        for h in past:
            with st.chat_message('user',avatar='🧑‍🎓'): st.write(h['prompt'])
            with st.chat_message('assistant',avatar='🤖'): st.markdown(h['answer']); st.caption(h['mode'])
        prompt=st.chat_input('Misalnya: Jelaskan tesis. Lalu: Bisa beri contoh lain?',max_chars=6000)
        if prompt:
            try:
                with st.spinner('Tutor sedang menyiapkan jawaban...'): core.ask(uid,selected,prompt,KEY,MODEL,topic)
                st.rerun()
            except (ValueError,RuntimeError) as e: st.error(str(e))
        if past: st.download_button('Unduh percakapan', '\n\n'.join('Siswa: '+h['prompt']+'\nTutor: '+h['answer'] for h in past),file_name='percakapan.txt')
        st.caption('Percakapan tersimpan. AI daring memakai 12 pasangan terakhir; tutor lokal mengikuti topik dan permintaan lanjutan sederhana. Jumlah pertanyaan tidak dibatasi.')

elif menu=='Latihan / kuis':
    st.subheader('📝 Uji pemahamanmu')
    pg,analysis=st.tabs(['Pilihan ganda','Latihan analisis & gagasan'])
    with pg:
        if identity_required():
            questions=core.quiz_questions()
            version=questions[0].get('version','legacy')
            st.caption('10 soal • benar = 10, salah = 0 • nilai maksimal 100. Kemampuan menulis dinilai terpisah melalui tugas artikel.')
            if st.session_state.quiz_result is not None and st.session_state.quiz_result.get('bank_version')!=version:
                st.session_state.quiz_result=None
                st.session_state.attempt=secrets.token_hex(12)
                st.info('Bank soal sudah diperbarui. Nilai percobaan lama tetap tersimpan; percobaan baru memakai 10 soal.')
            if st.session_state.quiz_result is None:
                with st.form('quiz'):
                    answers={}
                    for number,q in enumerate(questions,1):
                        answers[q['id']]=st.radio(f"{number}. {q['question']}",list(q['options']),index=None,format_func=lambda k,q=q:k+'. '+q['options'][k],key=st.session_state.attempt+q['id'])
                    clicked=st.form_submit_button('Kirim semua jawaban')
                if clicked:
                    try:
                        score=core.save_quiz(st.session_state.user['id'],st.session_state.attempt,answers)
                        st.session_state.quiz_result={'score':score,'answers':answers,'bank_version':version}; st.rerun()
                    except ValueError as e: st.error(str(e))
            else:
                result=st.session_state.quiz_result
                correct_count=sum(result['answers'][q['id']]==q['answer'] for q in questions)
                total=len(questions)
                columns=st.columns(3)
                columns[0].metric('✅ Benar',f'{correct_count} dari {total}')
                columns[1].metric('🔁 Salah',total-correct_count)
                columns[2].metric('📊 Nilai kuis / 100',f"{result['score']:.0f}".replace('.',','))
                st.info(f"Nilai = ({correct_count} ÷ {total}) × 100 = {result['score']:.0f}".replace('.',','))
                st.caption('Setiap soal mempunyai bobot yang sama; tidak ada pengurangan nilai untuk jawaban salah. Rubrik berbobot digunakan untuk tugas menulis artikel, bukan kuis pilihan ganda.')
                for q in questions:
                    correct=result['answers'][q['id']]==q['answer']
                    with st.expander(('✅ ' if correct else '🔁 ')+q['question']):
                        st.write('Jawabanmu:',result['answers'][q['id']]); st.write('Kunci:',q['answer']); st.write(q['explanation']); st.caption('Tingkat kognitif rancangan: '+q.get('bloom',''))
                if st.button('Latihan ulang (percobaan baru tersimpan terpisah)'):
                    st.session_state.quiz_result=None; st.session_state.attempt=secrets.token_hex(12); st.rerun()
            export(core.report('quizzes',st.session_state.user['id']),'hasil_kuis_saya.csv')
    with analysis:
        st.markdown(next(d['text'] for d in all_docs if d['file']=='08_latihan.txt'))
        st.text_area('Catatan latihanmu (untuk latihan mandiri pada sesi ini)',height=220)
        st.caption('Untuk tanggapan tutor, salin jawaban ini ke Tanya jawab AI Tutor. Catatan latihan ini belum dikumpulkan kepada guru.')

elif menu=='Brainstorming & kerangka':
    st.subheader('💡 Dari kata kunci menjadi bahan tulisan')
    st.write('Isi topik dan ide awalmu. Kamu boleh mulai dengan kata kunci sederhana. Hasilnya berupa usulan pengembangan yang masih perlu kamu periksa dan tulis ulang.')
    if identity_required():
        uid=st.session_state.user['id']
        records=core.brainstorm_history(uid)
        previous=json.loads(records[0]['inputs']) if records else {}
        with st.form('brainstorm_form'):
            topic=st.text_input('Isu pilihanmu',value=previous.get('topic',''),placeholder='Sampah plastik di kantin sekolah',max_chars=2000)
            thesis=st.text_area('Pendapat / kesan awal',value=previous.get('thesis',''),placeholder='Misalnya: kotor, bau',max_chars=2000)
            reason1=st.text_area('Alasan pertama',value=previous.get('reason1',''),placeholder='Misalnya: membuang sampah sembarangan',max_chars=2000)
            reason2=st.text_area('Alasan kedua',value=previous.get('reason2',''),placeholder='Misalnya: penggunaan plastik berlebihan',max_chars=2000)
            counter=st.text_area('Pandangan lain / kendala (boleh belum tahu)',value=previous.get('counter',''),max_chars=2000)
            ending=st.text_area('Solusi yang terpikir',value=previous.get('ending',''),placeholder='Misalnya: daur ulang',max_chars=2000)
            clicked=st.form_submit_button('✨ Kembangkan ide menjadi bahan tulisan')
        if clicked:
            try:
                with st.spinner('Mengembangkan arah tulisan...'):
                    core.brainstorm(uid,dict(topic=topic,thesis=thesis,reason1=reason1,reason2=reason2,counter=counter,ending=ending),KEY,MODEL)
                st.rerun()
            except (ValueError,RuntimeError) as e: st.error(str(e))
        records=core.brainstorm_history(uid)
        if records:
            choice=st.selectbox('Hasil pengembangan tersimpan',range(len(records)),format_func=lambda i:json.loads(records[i]['inputs'])['topic']+' • '+records[i]['created'])
            result=records[choice]
            st.markdown(result['answer'])
            st.download_button('⬇️ Unduh hasil pengembangan',result['answer'],file_name='pengembangan_ide.txt')
        st.caption('Tidak ada batas jumlah pengembangan per akun. Hasil tersimpan pada akunmu; isian yang belum dikirim belum disimpan. Tanpa API, hasil memakai pola lokal, bukan model generatif.')

elif menu=='Evaluasi & refleksi':
    st.subheader('📄 Saatnya menulis artikelmu')
    st.markdown(next(d['text'] for d in all_docs if d['file']=='09_evaluasi.txt'))
    if identity_required():
        with st.form('submission'):
            title=st.text_input('Judul artikel',max_chars=160)
            body=st.text_area('Isi artikel 500–700 kata (tanpa judul / sumber)',height=330,max_chars=20000)
            sources=st.text_area('Minimal dua sumber: penulis/lembaga, tahun, judul, tautan; satu per baris',max_chars=5000)
            reflection=st.text_area('Refleksi: kesulitanmu, revisi yang dilakukan, dan bantuan AI yang digunakan',max_chars=4000)
            clicked=st.form_submit_button('Kumpulkan untuk guru')
        if clicked:
            try:
                core.submit(st.session_state.user['id'],title,body,sources,reflection); st.success('Artikel tersimpan. Buka Umpan balik AI atau tunggu penilaian guru.')
            except ValueError as e: st.error(str(e))
        st.subheader('Riwayat tulisan dan penilaianmu')
        for s in core.submissions(st.session_state.user['id']):
            with st.expander(s['title']+' • '+s['created']):
                st.write(s['body']); st.write('Sumber:',s['sources']); st.write('Refleksi:',s['reflection'])
                if s['teacher_scores']:
                    scores=json.loads(s['teacher_scores']); score=core.weighted(scores)
                    st.success(f'Nilai guru: {score} — {core.category(score)}'); st.write(scores); st.write(s['teacher_notes'])
                else: st.info('Belum dinilai guru.')

elif menu=='Umpan balik AI':
    st.subheader('🔍 Revisi satu langkah lebih baik')
    st.markdown(next(d['text'] for d in all_docs if d['file']=='07_rubrik.txt'))
    if identity_required():
        uid=st.session_state.user['id']; items=core.submissions(uid)
        if not items: st.info('Kumpulkan artikel di Evaluasi & refleksi terlebih dahulu.')
        else:
            selected=st.selectbox('Artikel',range(len(items)),format_func=lambda i:items[i]['title']+' • '+items[i]['created'])
            s=items[selected]
            if s['ai_feedback']: st.markdown(s['ai_feedback'])
            st.caption('Umpan balik AI bersifat formatif. Tidak ada batas jumlah permintaan per akun. Guru menentukan nilai akhir.')
            if st.button('Minta umpan balik AI',disabled=not KEY):
                try:
                    with st.spinner('Membaca artikel...'): core.feedback(s['id'],uid,KEY,MODEL)
                    st.rerun()
                except (ValueError,RuntimeError) as e: st.error(str(e))
            if not KEY: st.info('API belum diaktifkan. Gunakan rubrik untuk menilai diri dan minta masukan guru.')

elif menu=='Panduan pemakaian':
    st.markdown('''### Belajar dalam lima langkah
1. Daftar dengan username, nama, kelas, dan kata sandi. Gunakan akun yang sama agar hasil tidak terpencar.
2. Baca CP, tujuan, materi, struktur, dan kebahasaan. Favoritkan materi dan tandai selesai.
3. Pelajari contoh, tandai gagasan, lalu susun kerangka. Tekan Kembangkan ide; hasil dan riwayat pengembangan tersimpan pada akunmu dan dapat diunduh.
4. Kerjakan kuis sampai lengkap. Hasil dan setiap percobaan tersimpan untuk guru.
5. Tulis 500–700 kata, cantumkan dua sumber, dan kumpulkan. Gunakan masukan AI untuk revisi; kirim revisi sebagai tulisan baru.

### Bertanya kepada tutor
Tanyakan “Apa itu tesis?”, lalu “Beri contoh tentang sampah sekolah”, atau “Apa bedanya dengan topik?”. Pilih **Semua materi** jika ingin berpindah topik. Percakapan dapat dilanjutkan dan dibuka kembali setelah masuk. Jumlah interaksi per akun tidak dibatasi. Layanan API tetap mengikuti saldo dan batas penyedia. Riwayat tersimpan, tetapi konteks AI dibatasi 12 pasangan terakhir.

### Akun guru
Guru masuk melalui Dasbor guru menggunakan kata sandi khusus yang ditetapkan pengelola. Guru dapat membaca absensi, kemajuan, hasil kuis, tulisan, refleksi dan riwayat interaksi; memberi skor rubrik; serta mengunduh rekap CSV.

### Mode aplikasi
Tanpa API, materi, kuis 10 soal, pengumpulan artikel, rekap, jawaban lokal terarah, dan brainstorming berbasis pola tersedia. AI daring membutuhkan koneksi internet serta kunci API milik pengelola. Teks pertanyaan dan potongan materi dikirim ke penyedia AI; artikel dikirim ketika siswa meminta umpan balik. Nama, username, dan kata sandi tidak disisipkan ke permintaan AI. Hasil AI perlu diperiksa, terutama fakta dan sumber.
''')

elif menu=='Dasbor guru':
    st.subheader('👩‍🏫 Ruang guru')
    if not TEACHER:
        st.warning('Pengelola perlu mengatur TEACHER_PASSWORD sebelum dasbor dapat digunakan.')
    elif not st.session_state.teacher:
        with st.form('teacher_login'):
            password=st.text_input('Kata sandi guru',type='password'); clicked=st.form_submit_button('Masuk sebagai guru')
        if clicked:
            if hmac.compare_digest(password,TEACHER): st.session_state.teacher=True; st.rerun()
            else: st.error('Kata sandi guru tidak sesuai.')
    else:
        tab=st.selectbox('Data',['Daftar siswa','Absensi','Kemajuan materi','Kuis','Artikel & penilaian','Interaksi tutor'])
        tables={'Absensi':'attendance','Kemajuan materi':'progress','Kuis':'quizzes','Interaksi tutor':'messages'}
        if tab=='Daftar siswa':
            rows=core.students()
            classroom=st.selectbox('Filter kelas',['Semua kelas']+sorted(set(r['class'] for r in rows)))
            filtered=[r for r in rows if classroom=='Semua kelas' or r['class']==classroom]
            st.dataframe(filtered,width='stretch'); export(filtered,'daftar_siswa.csv')
        elif tab in tables:
            rows=core.report(tables[tab]); classes=sorted(set(r['class'] for r in rows))
            classroom=st.selectbox('Filter kelas',['Semua kelas']+classes)
            filtered=[r for r in rows if classroom=='Semua kelas' or r['class']==classroom]
            st.dataframe(filtered,width='stretch'); export(filtered,tables[tab]+'.csv')
        else:
            items=core.submissions(); classes=sorted(set(r['class'] for r in items))
            classroom=st.selectbox('Filter kelas',['Semua kelas']+classes)
            items=[r for r in items if classroom=='Semua kelas' or r['class']==classroom]
            if not items: st.info('Belum ada artikel.')
            else:
                selected=st.selectbox('Tulisan siswa',range(len(items)),format_func=lambda i:items[i]['name']+' • '+items[i]['title']+' • '+items[i]['created'])
                s=items[selected]; st.write(s['body']); st.write('Sumber siswa:',s['sources']); st.write('Refleksi:',s['reflection'])
                with st.expander('Umpan balik AI'): st.write(s['ai_feedback'] or 'Belum diminta.')
                old=json.loads(s['teacher_scores']) if s['teacher_scores'] else {}
                with st.form('grading-'+s['id']):
                    scores={k:st.slider(k+f' ({w}%)',1,4,old.get(k,3)) for k,w in core.WEIGHTS.items()}
                    notes=st.text_area('Catatan revisi untuk siswa',value=s['teacher_notes'] or '')
                    clicked=st.form_submit_button('Simpan nilai guru')
                if clicked: core.grade_submission(s['id'],scores,notes); st.success('Nilai tersimpan.'); st.rerun()
                if s['teacher_scores']:
                    score=core.weighted(old); st.metric('Nilai akhir tulisan',score); st.write(core.category(score))
                rows=[]
                for item in items:
                    value=core.weighted(json.loads(item['teacher_scores'])) if item['teacher_scores'] else None
                    rows.append({**item,'nilai_guru':value,'kategori':core.category(value) if value is not None else 'Belum dinilai'})
                export(rows,'artikel_dan_nilai.csv')
        st.caption('Data tersimpan di database online.' if core.persistent() else 'Mode lokal: cadangkan file database. Penyimpanan permanen online belum aktif.')
