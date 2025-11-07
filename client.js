// client.js
const socket = io();
const username = window.username || prompt("نام کاربری؟") || ("مهمان_"+Math.random().toString(36).slice(2,8));
document.getElementById('me') && (document.getElementById('me').textContent = username);

// join
socket.emit('join', {username: username});

// CHAT
const chatbox = document.getElementById('chatbox');
function addChat(from, text){
  const el = document.createElement('div'); el.className='msg';
  el.innerHTML = `<strong>${from}</strong><div>${text}</div>`;
  chatbox.appendChild(el); chatbox.scrollTop = chatbox.scrollHeight;
}
socket.on('chat', d=> addChat(d.from, d.text));
socket.on('system', txt => addChat('سیستم', txt));

// SEND chat
document.getElementById('sendchat') && document.getElementById('sendchat').addEventListener('click', ()=>{
  const inp = document.getElementById('chatinput'); const v = inp.value.trim(); if(!v) return;
  socket.emit('chat', {username: username, text: v});
  inp.value = '';
});

// PLAY: start & submit
let timerEl = document.getElementById('timer');
let letterEl = document.getElementById('letter');
let roundActive = false;

document.getElementById('start') && document.getElementById('start').addEventListener('click', ()=>{
  socket.emit('start_round');
});

socket.on('round_started', d=>{
  roundActive = true;
  letterEl.textContent = d.letter;
  let remain = d.duration;
  timerEl.textContent = new Date(remain*1000).toISOString().substr(14,5);
});
socket.on('time_update', d=>{
  let s = d.time_left; timerEl.textContent = new Date(s*1000).toISOString().substr(14,5);
});
socket.on('round_ended', d=>{
  roundActive = false; alert('دور پایان یافت!'); timerEl.textContent='00:00';
});

// submit answers
document.getElementById('submit') && document.getElementById('submit').addEventListener('click', ()=>{
  const answers = {
    name: document.getElementById('name').value,
    lastname: document.getElementById('lastname').value,
    city: document.getElementById('city').value,
    country: document.getElementById('country').value,
    animal: document.getElementById('animal').value,
    color: document.getElementById('color').value,
    object: document.getElementById('object').value
  };
  socket.emit('submit_answers', {username: username, answers: answers});
});

socket.on('submission_result', d=>{
  if(d.ok){
    alert(`امتیاز کسب شده: ${d.earned}\nمجموع شما: ${d.total}`);
  } else {
    alert(d.message || 'خطا در ثبت');
  }
});

// leaderboard updates
socket.on('player_list', d=>{
  const list = d.players || [];
  const container = document.getElementById('leaderboard');
  if(!container) return;
  container.innerHTML = '';
  list.sort((a,b)=> (b.score||0) - (a.score||0));
  list.forEach((p, i)=>{
    const r = document.createElement('div'); r.className='rank';
    const pos = document.createElement('div'); pos.className='pos pos-'+(i+1); pos.textContent = i+1;
    const meta = document.createElement('div'); meta.className='meta';
    meta.innerHTML = `<div><strong>${p.username}</strong><div class="small">${p.score} امتیاز</div></div>`;
    r.appendChild(pos); r.appendChild(meta);
    container.appendChild(r);
  });
});

// receive initial data
socket.on('joined', d=>{
  if(d.scores){ /* populate maybe */ }
});