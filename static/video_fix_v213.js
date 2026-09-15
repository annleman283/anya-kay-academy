/* ANYA KAY Academy v2.13 — uploaded video playback fix. UI only; no DB changes. */
(function(){
  var videoUrls=[];
  function revokeVideos(){videoUrls.forEach(function(u){try{URL.revokeObjectURL(u)}catch(e){}});videoUrls=[]}

  window.playMaterialVideo=async function(materialId,url,title){
    var box=document.getElementById('material-video-'+materialId);
    if(!box)return;
    box.innerHTML='<div class="label">ЗАГРУЖАЕМ ВИДЕО…</div><div class="progressbar"><i id="material-video-progress-'+materialId+'" style="width:8%"></i></div><p class="label">Первый запуск может занять немного времени.</p>';
    try{
      var r=await fetch(url,{headers:headers(),cache:'no-store'});
      if(!r.ok)throw new Error('HTTP '+r.status);
      var total=Number(r.headers.get('Content-Length')||0),loaded=0,blob;
      if(r.body&&r.body.getReader){
        var reader=r.body.getReader(),chunks=[];
        while(true){var part=await reader.read();if(part.done)break;chunks.push(part.value);loaded+=part.value.byteLength;var p=document.getElementById('material-video-progress-'+materialId);if(p&&total)p.style.width=Math.max(8,Math.min(95,Math.round(loaded/total*100)))+'%'}
        blob=new Blob(chunks,{type:r.headers.get('Content-Type')||'video/mp4'});
      }else blob=await r.blob();
      if(!blob.size)throw new Error('empty video');
      var objectUrl=URL.createObjectURL(blob);videoUrls.push(objectUrl);
      box.innerHTML='<div class="video material-video"><video id="material-player-'+materialId+'" controls playsinline webkit-playsinline preload="metadata" poster=""><source src="'+objectUrl+'" type="'+esc(blob.type||'video/mp4')+'"></video></div>';
      var v=document.getElementById('material-player-'+materialId);
      if(v){v.load();var pr=v.play();if(pr&&pr.catch)pr.catch(function(){})}
    }catch(e){
      box.innerHTML='<div class="notice"><b>Видео не удалось загрузить</b><p>Попробуй открыть его ещё раз. Если проблема повторится, перезагрузи Academy.</p><button class="mini" onclick="playMaterialVideo('+materialId+',\''+String(url).replace(/'/g,"\\'")+'\',\''+String(title||'Видео').replace(/'/g,"\\'")+'\')">Повторить →</button></div>';
    }
  };

  var baseRender=window.renderLesson;
  window.renderLesson=function(){
    revokeVideos();
    var l=S.lesson;
    if(!l)return baseRender();
    var video=l.youtube_id?'<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/'+encodeURIComponent(l.youtube_id)+'?rel=0" title="'+esc(l.title)+'" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe></div>':(l.direct_video_url?'<div class="video"><video src="'+esc(l.direct_video_url)+'" controls playsinline webkit-playsinline preload="metadata"></video></div>':'<div class="card">Видео пока не загружено.</div>');
    var desc=l.description?'<div class="card readable preserve">'+esc(l.description)+'</div>':'';
    var mats=l.materials.map(function(m){
      var du=encodeURIComponent(m.download_url),tt=encodeURIComponent(m.caption||'Материал');
      if(m.file_type==='video'){
        var vu=m.view_url||m.download_url;
        return '<div class="card material video-material-card"><div class="grow"><div class="title preserve">'+esc(m.caption||'Дополнительное видео')+'</div><div id="material-video-'+m.id+'" class="material-video-launch"><button class="btn secondary" onclick="playMaterialVideo('+m.id+',\''+String(vu).replace(/'/g,"\\'")+'\',\''+String(m.caption||'Видео').replace(/'/g,"\\'")+'\')">▶ Смотреть видео</button></div></div></div>';
      }
      return '<div class="card material"><div class="thumb">'+(m.file_type==='presentation'?'PPT':'FILE')+'</div><div class="grow"><div class="title preserve">'+esc(m.caption||'Материал')+'</div><div class="material-actions"><button class="mini downloadonly" onclick="event.stopPropagation();downloadMaterial(decodeURIComponent(\''+du+'\'),decodeURIComponent(\''+tt+'\'))">↓ Скачать материал</button></div></div></div>';
    }).join('');
    var primary=l.questions.length?'<button class="btn" onclick="startQuiz()">Перейти к тесту →</button>':'<button class="btn" onclick="completeLesson()">Завершить урок →</button>';
    shell('<div class="top"><button class="mini" onclick="learn()">‹ Назад</button><button class="mini" onclick="toggleBookmark()">'+(l.bookmarked?'♥':'♡')+'</button></div><div class="label">'+lessonLabel(l)+'</div><h1 class="section-title">'+esc(l.title.replace(/^Урок\\s*\\d+\\.?\\s*/i,''))+'</h1>'+video+desc+(mats?'<h3>Материалы к уроку</h3>'+mats:'')+primary+'<button class="btn secondary" onclick="askAnya()">Задать вопрос Ане</button><div class="card note-card"><div class="title">Мои заметки</div><textarea id="note" class="field admin-textarea" rows="5" placeholder="Запиши важную мысль…">'+esc(l.note||'')+'</textarea><button id="saveNoteBtn" class="mini" onclick="saveNote()">Сохранить заметку</button></div>','learn');
  };
})();
