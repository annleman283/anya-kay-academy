/* ANYA KAY Academy v2.10 — safe UI-only patch.
   No database writes/migrations. Existing lesson progress, attempts and answers are untouched. */
(function(){
  function renderHomeSafe(){
    var d=S.data,p=d.progress,cur=d.lessons.find(function(l){return l.state==='current'})||d.lessons[d.lessons.length-1],resume=false;
    try{resume=!!(cur&&localStorage.getItem('ak_quiz_'+cur.id))}catch(e){}
    shell('<div class="hero"><div><div class="label">ANYA KAY ACADEMY</div><h1 class="serif">Привет, '+esc(d.user.full_name||d.user.first_name)+'</h1><p>BASIC LASH COURSE</p></div><div class="ring" style="--p:'+p.percent+'"><b>'+p.percent+'%</b></div></div><div class="card next-step"><div class="label">ТВОЙ СЛЕДУЮЩИЙ ШАГ</div><div class="title next-title">'+esc(cur?cur.title:'Курс завершён')+'</div>'+(cur?'<button class="btn" onclick="openLesson('+cur.id+').then(function(){'+(resume?'startQuiz()':'')+'})">'+(resume?'Продолжить тест →':'Продолжить обучение →')+'</button>':'')+'</div><div class="statgrid"><div class="card stat"><b>'+p.completed+'/'+p.total+'</b><div class="label">Уроков</div></div><div class="card stat" role="button" tabindex="0" onclick="mistakes()"><b>'+d.mistakes.length+'</b><div class="label">Ошибок</div></div></div>','home');
  }

  function renderProfileSafe(){
    var d=S.data,p=d.progress,fr=p.final_result;
    var exam=fr?'<div class="card"><div class="label">ФИНАЛЬНЫЙ ЭКЗАМЕН</div><div class="title">Теория пройдена · '+Math.round(fr.score*100/fr.total)+'%</div></div>':'';
    shell('<h1 class="section-title">Мой профиль</h1><div class="center"><div class="avatar student-avatar" aria-label="Ученица"><span>♙</span></div><h2 class="serif profname">'+esc(d.user.full_name||d.user.first_name)+'</h2><div class="label">УЧЕНИЦА ANYA KAY ACADEMY</div></div><div class="statgrid"><div class="card stat"><b>'+p.percent+'%</b><div class="label">Прогресс</div></div><div class="card stat"><b>'+p.completed+'</b><div class="label">Уроков</div></div><div class="card stat" role="button" tabindex="0" onclick="mistakes()"><b>'+d.mistakes.length+'</b><div class="label">Ошибок</div></div></div>'+exam+'<div class="card action" onclick="mistakes()"><b class="grow">✕ Мои ошибки</b><span>›</span></div><div class="card action" onclick="notes()"><b class="grow">▧ Мои заметки</b><span>›</span></div><div class="card action" onclick="saved()"><b class="grow">♡ Сохранённое</b><span>›</span></div><div class="card action" onclick="startTour(true)"><b class="grow">◎ Повторить экскурсию</b><span>›</span></div><div class="card action" onclick="finalIntro()"><b class="grow">▣ Финальный экзамен</b><span>›</span></div>'+(d.user.is_admin?'<button class="btn adminbtn" onclick="adminPanel()">Панель администратора</button>':''),'profile');
  }

  function renderFinalIntroSafe(){
    var p=S.data.progress;
    var ready=p.completed>=p.total || !!(S.data.user&&S.data.user.is_admin);
    if(p.final_passed)return celebration(true);
    shell('<button class="mini" onclick="profile()">‹ Назад</button><h1 class="section-title">Финальный экзамен</h1><div class="card"><b>24 вопроса по всей теоретической части</b><p>Проходной результат — <b>70%</b>.</p><p class="label">Вопросы и варианты ответов перемешиваются. Если не получится с первого раза, экзамен можно пройти ещё раз.</p></div>'+(ready?'<button class="btn" onclick="startFinal()">Начать экзамен →</button>':'<div class="notice">Сначала заверши все уроки. Сейчас пройдено '+p.completed+' из '+p.total+'.</div>'),'profile');
  }

  /* Override UI navigation only after the main app has loaded. */
  window.home=renderHomeSafe;
  window.profile=renderProfileSafe;
  window.finalIntro=renderFinalIntroSafe;
})();
