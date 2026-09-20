<script lang="ts">
  import { onMount } from 'svelte';
  import { loadCourses, loadCourse, foundationCourse, type Course, type CourseSummary, type Lesson } from './courses';
  import { trainerAction } from './gateway';
  import { invoke, isTauri } from '@tauri-apps/api/core';

  let { profile, connected, onProfile, onSettings, onServices, onBuild } = $props<{
    profile: { name: string; avatar: string }; connected:boolean; onProfile: () => void; onSettings: () => void; onServices: () => void; onBuild:(practice:boolean)=>void;
  }>();
  let courses = $state<CourseSummary[]>([]);
  let course = $state<Course>(foundationCourse);
  let lessonIndex = $state(0);
  let layer = $state<'explanation'|'syntax'|'rationale'>('explanation');
  let rightTab = $state<'task'|'coach'>('coach');
  let practicePage = $state<'observe'|'next'>('observe');
  let busy = $state(false); let error = $state(''); let status = $state('');
  let coachBusy = $state(false); let coachError = $state('');
  let coach = $state<{question:string; options:string[]; correctIndex:number; feedback:string; reflectionPrompt:string; evidenceType:string}|null>(null);
  let selectedOption = $state<number|null>(null); let answer = $state(''); let answerFeedback = $state('');
  let taskBusy = $state(false); let taskError = $state('');
  let task = $state<{prompt:string; requiredFiles:string[]; acceptance:string[]}|null>(null);
  const lesson = $derived(course.lessons[lessonIndex] as Lesson);
  const canSubmitCode = $derived(course.id !== foundationCourse.id && !!lesson.practiceTask);
  const route = $derived(course.lessons.map((item, index) => ({...item, index, state: index < lessonIndex ? 'done' : index === lessonIndex ? 'current' : 'next'})));
  const layers = [['explanation','人话'],['syntax','拆开看'],['rationale','为什么要这样']] as const;
  function message(value: unknown) { return value instanceof Error ? value.message : String(value); }

  async function loadLibrary() {
    busy = true; error = '';
    try { courses = await loadCourses(); } catch { courses = []; }
    finally { busy = false; }
  }
  async function chooseCourse(id: string) {
    busy = true; error = ''; status = '';
    try { course = await loadCourse(id); lessonIndex = 0; resetLesson(); }
    catch (e) { error = message(e); }
    finally { busy = false; }
  }
  function chooseLesson(index: number) { lessonIndex = index; resetLesson(); }
  function resetLesson() {
    layer='explanation'; practicePage='observe'; rightTab=lesson?.practiceTask ? 'task' : 'coach';
    coach=null; coachError=''; selectedOption=null; answer=''; answerFeedback=''; task=lesson?.practiceTask ?? null; taskError='';
  }
  async function generateCoach() {
    if (coachBusy) return;
    coachBusy=true; coachError=''; selectedOption=null;
    try {
      coach = await trainerAction('coach-turn', { skillId:'core.adaptive-teaching', lessonTitle:lesson.title,
        code:lesson.code, language:lesson.language, layer, focusTitle:'观察与练习', focusContent:lesson.exercise,
        reflectionContext:lesson.reflection });
    } catch(e) { coachError = message(e); }
    finally { coachBusy=false; }
  }
  async function saveAnswer() {
    const text=answer.trim(); if (text.length < 6) { answerFeedback='请写出具体判断和依据（至少 6 个字）。'; return; }
    busy=true; answerFeedback='';
    try {
      if (course.id !== foundationCourse.id) {
        const assessment = await trainerAction<{score:number;feedback:string;quote:string;nextStep:string}>('assessment', {
          planId:course.id, lessonId:lesson.id, answer:text, evidenceType:coach?.evidenceType ?? 'reflection',
          question:coach?.reflectionPrompt ?? lesson.reflection, activity:'coach-text' });
        answerFeedback=`${assessment.score >= 2 ? '回答通过' : '需要补充'} · ${assessment.score}/4\n${assessment.feedback}\n下一步：${assessment.nextStep}`;
        if (assessment.score < 2) return;
      }
      await trainerAction('evidence-save', { conceptId:`programming:${course.id}:${lesson.id}`, level:1,
        evidenceType:coach?.evidenceType ?? 'reflection', note:text, language:lesson.language });
      answerFeedback = (answerFeedback ? answerFeedback+'\n' : '') + '学习凭据已保存。';
    } catch(e) { answerFeedback='保存失败：'+message(e); }
    finally { busy=false; }
  }
  async function prepareTask() {
    if (course.id === foundationCourse.id) return;
    taskBusy=true; taskError='';
    try { const value=await trainerAction<{task:{prompt:string;requiredFiles:string[];acceptance:string[]}}>('lesson-task-prepare',{planId:course.id,lessonId:lesson.id}); task=value.task; }
    catch(e){ taskError=message(e); } finally{taskBusy=false;}
  }
  async function inspectSubmission() {
    taskBusy=true; taskError=''; status='';
    try { await trainerAction('submission-config'); status='提交服务已就绪；请在连接管理中关联课程工作区。'; }
    catch(e){ taskError=message(e); } finally{taskBusy=false;}
  }
  async function importProject() {
    if (!isTauri()) { status='请在 Windows 桌面客户端中选择项目目录。'; return; }
    busy=true; error=''; status='';
    try {
      const job=await invoke<{id:string;project?:{name:string;fileCount:number}}>('import_project');
      status=`已建立 ${job.project?.name??'项目'} 的安全摘要，正在生成候选教学；可在“服务与连接设置 → 生成任务”查看进度。`;
    } catch(e) { const value=message(e); if(!value.includes('取消选择')) error=value; }
    finally{busy=false;}
  }
  onMount(loadLibrary);
</script>

<div class="trainer-workspace">
  <aside class="learning-sidebar glass-pane">
    <div class="trainer-brand"><div><strong>Trainer</strong><span>你的 AI 技术导师</span></div><button class="icon-button" aria-label="收起侧边栏">◧</button></div>
    <div class="soft-divider"></div>
    <section class="side-section">
      <p class="section-label">开始学习</p>
      <div class="project-entry">
        <div class="entry-title"><span class="blue-orb">⌁</span><div><strong>项目教学</strong><small>{course.title}</small></div></div>
        <p>从项目生成课程，在实践中补齐基础。</p>
        <button class="primary wide" disabled={busy} onclick={importProject}><span>▱＋</span> {busy?'正在处理…':'导入项目'} <span>→</span></button>
        <button class="link-button" onclick={() => (document.getElementById('course-select') as HTMLSelectElement)?.focus()}>▣ 打开教学入口</button>
      </div>
      <div class="side-actions"><button onclick={() => onBuild(false)}>＋ 创建课程</button><button onclick={() => onBuild(true)}>⚒ 项目实战</button></div>
    </section>
    <div class="connection-row"><span class:offline={!connected} class="status-dot"></span><span>{connected?'本地服务已连接':'等待本地服务'}</span><button class="icon-button" onclick={onServices}>•••</button></div>
    <div class="soft-divider"></div>
    <div class="route-heading"><span class="section-label">学习路线</span><select id="course-select" value={course.id} onchange={(e)=>chooseCourse(e.currentTarget.value)}><option value={foundationCourse.id}>编程基础</option>{#each courses as item}<option value={item.id}>{item.title}</option>{/each}</select></div>
    <div class="lesson-route">
      {#each route as item}
        <button class:active={item.state==='current'} onclick={()=>chooseLesson(item.index)}>
          <span class="route-dot {item.state}">{item.state==='done'?'✓':''}</span><span><strong>{item.title}</strong><small>第 {item.index+1} 步 · {item.state==='current'?'正在学习':item.state==='done'?'已完成练习':'下一步'}</small></span>
        </button>
      {/each}
    </div>
    <button class="knowledge-button" onclick={() => status='知识库管理将在下一阶段并入此窗口。'}>▥ 浏览 Skill 知识库</button>
    <button class="profile-strip" onclick={onProfile}><span class="avatar">{profile.avatar || '🧑‍💻'}</span><span><strong>{profile.name || '学习者'}</strong><small>能力 · 活动 · 成就</small></span><b>›</b></button>
  </aside>

  <main class="lesson-canvas">
    <div class="canvas-scroll">
      {#if error}<div class="notice">{error}</div>{/if}{#if status}<div class="status-banner">{status}<button onclick={()=>{status='';}} aria-label="关闭提示">×</button></div>{/if}
      <header class="lesson-header"><div><span>当前任务</span><h1>{lesson.title}</h1><p>{lesson.objective}</p></div><span class="language-pill">▤ {lesson.language}</span></header>
      <section class="code-card"><div class="code-toolbar"><span>示例代码</span><button onclick={()=>navigator.clipboard.writeText(lesson.code)}>复制代码</button></div><pre><code>{lesson.code}</code></pre></section>
      <section class="teaching-block">
        <div class="block-title"><h2>▤ 课程讲解</h2><span> Aa&nbsp; 排版阅读⌄</span></div>
        <div class="segmented teaching-tabs">{#each layers as [key,label]}<button class:active={layer===key} onclick={()=>layer=key}>{label}</button>{/each}</div>
        <div class="glass-card prose"><h3>{layers.find(([key])=>key===layer)?.[1]}</h3><p>{lesson[layer]}</p></div>
      </section>
      <section class="practice-stage glass-card">
        <div class="stage-tabs"><button class:active={practicePage==='observe'} onclick={()=>practicePage='observe'}>观察与练习</button><button class:active={practicePage==='next'} onclick={()=>practicePage='next'}>完成本课</button></div>
        {#if practicePage==='observe'}
          <h2>观察与练习</h2><p class="large-reading">{lesson.exercise}</p><div class="soft-divider"></div><h3>用自己的话解释</h3><p>{lesson.reflection}</p>
          {#if canSubmitCode}<button class="secondary" onclick={()=>rightTab='task'}>打开代码任务 · 查看要求并提交 →</button>{/if}
        {:else}
          <div class="completion"><span>✓</span><div><h2>准备进入下一步</h2><p>先在右侧完成本课回讲；课程代码任务以实际工作区评审为准。</p></div></div>
          <button class="primary" disabled={lessonIndex===course.lessons.length-1} onclick={()=>chooseLesson(lessonIndex+1)}>下一课 →</button>
        {/if}
      </section>
    </div>
  </main>

  <aside class="coach-pane glass-pane">
    {#if canSubmitCode}<div class="coach-switch"><strong>本课操作</strong><div class="segmented"><button class:active={rightTab==='task'} onclick={()=>rightTab='task'}>代码任务</button><button class:active={rightTab==='coach'} onclick={()=>rightTab='coach'}>AI 教练 · 答题</button></div></div>{/if}
    <div class="coach-scroll">
      {#if rightTab==='task' && canSubmitCode}
        <section class="coach-section"><h2>⚒ 本课代码任务</h2><p class="muted">提交本课代码教学要求完成的成果，不使用教练追问题替代课程实践。</p>
          {#if task}<div class="task-card"><h3>{task.prompt}</h3><h4>任务文件</h4>{#each task.requiredFiles as file}<code class="file-chip">{file}</code>{/each}<h4>验收要求</h4><ol>{#each task.acceptance as item}<li>{item}</li>{/each}</ol></div>
          {:else}<button class="primary" disabled={taskBusy} onclick={prepareTask}>{taskBusy?'正在准备…':'准备本课代码任务'}</button>{/if}
          <button class="primary wide" disabled={taskBusy || !task} onclick={inspectSubmission}>⇧ 提交并检查</button>
          {#if taskError}<div class="inline-error">{taskError}</div>{/if}</section>
      {:else}
        <section class="coach-section"><h2>✦ AI 教练</h2><p>跟随中栏「观察与练习」完成一个具体判断，再用自己的话说明依据。</p><small>当前课程语言：{lesson.language}</small>
          <div class="sync-card"><span>↻</span><div><strong>已同步 · 观察与练习</strong><small>问题和回讲直接取自本课练习；示例代码只作为参考。</small></div></div>
          {#if coachBusy}<div class="coach-loading"><span class="spinner"></span><strong>AI 正在根据本课内容设计问题与反馈…</strong><i></i><i></i><i></i></div>
          {:else if coach}
            <h3>本课回讲</h3><p class="coach-question">{coach.question}</p>{#each coach.options as option,index}<button class:selected={selectedOption===index} class="option" onclick={()=>selectedOption=index}><span>{selectedOption===index?'◉':'○'}</span>{option}</button>{/each}
            {#if selectedOption!==null}<div class:correct={selectedOption===coach.correctIndex} class="feedback">{selectedOption===coach.correctIndex?'判断正确。':'再看一下本课内容。'} {coach.feedback}</div>{/if}
          {:else}<h3>本课回讲</h3><p class="coach-question">{lesson.reflection}</p><button class="secondary" onclick={generateCoach}>生成本课 AI 问题</button>{/if}
          {#if coachError}<div class="inline-error">AI 教练暂不可用：{coachError}<button onclick={onServices}>检查 AI 服务</button></div>{/if}
          <div class="soft-divider"></div><h3>练习思路 · 文字回答</h3><p class="muted">{coach?.reflectionPrompt ?? lesson.reflection}</p>
          <textarea bind:value={answer} rows="5" placeholder="写下你的回答和判断依据…"></textarea><button class="primary" disabled={busy} onclick={saveAnswer}>{busy?'正在评判…':course.id===foundationCourse.id?'保存练习记录':'提交回答并评判'}</button>
          {#if answerFeedback}<div class="answer-feedback">{answerFeedback}</div>{/if}
          <div class="soft-divider"></div><h3>遇到别的问题？</h3><p class="muted">在创建课程中描述问题，Trainer 会识别需要补齐的基础与项目技能。</p>
        </section>
      {/if}
    </div>
    <button class="settings-dock" onclick={onSettings}>⚙ 服务与连接设置</button>
  </aside>
</div>
<style>.status-dot.offline{background:#7d7a83;box-shadow:none}</style>
