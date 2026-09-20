<script lang="ts">
  import { onMount } from 'svelte';
  import { loadCourses, loadCourse, type CourseSummary, type Course } from './courses';

  let courses = $state<CourseSummary[]>([]);
  let course = $state<Course | null>(null);
  let selectedId = $state('');
  let lessonIndex = $state(0);
  let tab = $state<'explanation' | 'syntax' | 'rationale'>('explanation');
  let listBusy = $state(false);
  let courseBusy = $state(false);
  let listError = $state('');
  let courseError = $state('');
  let listRequest = 0;
  let courseRequest = 0;
  let alive = true;
  const lesson = $derived(course?.lessons[lessonIndex]);
  const tabs = [['explanation', '人话讲解'], ['syntax', '拆开看'], ['rationale', '为什么这样']] as const;
  const typeLabels = { 'project-brief': '项目说明', concept: '知识讲解', implementation: '动手实现', verification: '测试验收' };
  function errorText(error: unknown) { return error instanceof Error ? error.message : String(error); }

  async function refresh() {
    const request = ++listRequest;
    listBusy = true; listError = '';
    try {
      const next = await loadCourses();
      if (!alive || request !== listRequest) return;
      courses = next;
      if (selectedId && !next.some(item => item.id === selectedId)) {
        ++courseRequest; course = null; selectedId = ''; courseBusy = false; courseError = '';
      }
      if (!selectedId && next.length) await selectCourse(next[0].id);
    } catch (error) {
      if (alive && request === listRequest) listError = errorText(error);
    } finally { if (alive && request === listRequest) listBusy = false; }
  }
  async function selectCourse(id: string) {
    const request = ++courseRequest;
    selectedId = id; course = null; courseBusy = true; courseError = ''; lessonIndex = 0; tab = 'explanation';
    try {
      const next = await loadCourse(id);
      if (alive && request === courseRequest) course = next;
    } catch (error) {
      if (alive && request === courseRequest) courseError = errorText(error);
    } finally { if (alive && request === courseRequest) courseBusy = false; }
  }
  function selectLesson(index: number) { lessonIndex = index; tab = 'explanation'; }
  onMount(() => { void refresh(); return () => { alive = false; ++listRequest; ++courseRequest; }; });
</script>

<div class="course-library">
  <div class="library-heading"><div><h2>已保存课程</h2><p>直接读取本机课程，不调用 AI、不改动学习记录。</p></div><button class="refresh" disabled={listBusy} onclick={refresh}>{listBusy ? '正在读取…' : '刷新课程'}</button></div>
  {#if listError}<div class="notice" role="status">{listError}{#if courses.length}<br/>保留上次读取的课程列表。{/if}</div>{/if}
  {#if listBusy && !courses.length}
    <div class="loading-grid" aria-label="正在加载课程" aria-busy="true">{#each [1, 2, 3] as item}<div class="skeleton panel"></div>{/each}</div>
  {:else if !courses.length && !listError}
    <section class="panel empty"><h3>这里还没有已保存课程</h3><p>在 Mac 原版中生成课程，或完成账户课程同步后，点击刷新。隔离预览不会读取原版学习数据。</p></section>
  {/if}
  {#if courses.length}
    <div class="course-picker"><label for="saved-course">选择课程</label><select id="saved-course" value={selectedId} onchange={event => selectCourse(event.currentTarget.value)}>{#each courses as item (item.id)}<option value={item.id}>{item.title} · {item.lessonCount} 课</option>{/each}</select><span>{courses.length} 门课程</span></div>
    {#if courseBusy}
      <div class="reader-loading" aria-label="正在加载课程内容" aria-busy="true"><div class="panel skeleton"></div><div class="panel skeleton"></div></div>
    {:else if courseError}
      <div class="notice" role="status">{courseError}<button class="refresh retry" onclick={() => selectCourse(selectedId)}>重试打开</button></div>
    {:else if course && lesson}
      <div class="reader">
        <div class="lesson-outline"><div class="outline-heading"><strong>课程目录</strong><span>{lessonIndex + 1} / {course.lessons.length}</span></div><div class="lesson-buttons" aria-label="课程目录">{#each course.lessons as item, index (item.id)}<button class:chosen={index === lessonIndex} aria-current={index === lessonIndex ? 'step' : undefined} onclick={() => selectLesson(index)}><span class="lesson-number">{String(index + 1).padStart(2, '0')}</span><span>{item.title}</span></button>{/each}</div></div>
        <article class="lesson-content" aria-label={lesson.title}>
          <div class="lesson-heading"><span class="lesson-kind">{typeLabels[lesson.contentType]}</span><span class="language-tag">{lesson.language}</span><h2>{lesson.title}</h2><p>{lesson.objective}</p></div>
          <div class="reading-tabs" role="group" aria-label="讲解方式">{#each tabs as [key, label]}<button class:selected={tab === key} aria-pressed={tab === key} onclick={() => tab = key}>{label}</button>{/each}</div>
          <section class="reading-section"><h3>{tabs.find(([key]) => key === tab)?.[1]}</h3><div class="teaching-text">{lesson[tab]}</div></section>
          <section class="reading-section"><div class="code-heading"><h3>本课示例代码</h3><span>{lesson.language}</span></div><pre aria-label={`${lesson.language} 示例代码`}><code>{lesson.code}</code></pre></section>
          <section class="reading-section"><h3>观察与练习</h3><div class="teaching-text">{lesson.exercise}</div></section>
          {#if lesson.practiceTask}<section class="reading-section practice"><h3>本课代码任务</h3><div class="teaching-text">{lesson.practiceTask.prompt}</div><h4>任务文件</h4><div class="file-chips">{#each lesson.practiceTask.requiredFiles as file}<code>{file}</code>{/each}</div><h4>验收要求</h4><ol>{#each lesson.practiceTask.acceptance as item}<li>{item}</li>{/each}</ol><p class="read-only-note">当前跨平台版本提供课程阅读。工作区授权与提交尚未接通，请使用 Mac 原版提交成果。</p></section>{/if}
          <details class="reading-section"><summary>回顾与思考</summary><div class="teaching-text">{lesson.reflection}</div></details>
          <div class="lesson-pagination"><button disabled={lessonIndex === 0} onclick={() => selectLesson(lessonIndex - 1)}>← 上一课</button><span>{lessonIndex + 1} / {course.lessons.length}</span><button disabled={lessonIndex === course.lessons.length - 1} onclick={() => selectLesson(lessonIndex + 1)}>下一课 →</button></div>
        </article>
      </div>
    {/if}
  {/if}
</div>

<style>
  .course-library{min-width:0}.library-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:18px}.library-heading p{margin:8px 0 0}.loading-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.course-picker{display:flex;align-items:center;gap:12px;padding:16px 0 24px;min-width:0}.course-picker label,.course-picker>span{font-size:12px;color:#aaa6b8;flex-shrink:0}.course-picker select{min-width:0;flex:1;border:1px solid #ffffff20;border-radius:10px;background:#24212d;color:#eeedf5;padding:12px;font:inherit}.course-picker select:focus-visible{outline:2px solid #9c91ff;outline-offset:3px}.reader{display:grid;grid-template-columns:minmax(190px,240px) minmax(0,1fr);gap:26px;align-items:start}.reader-loading{display:grid;grid-template-columns:1fr 3fr;gap:26px}.reader-loading .skeleton{height:350px}.lesson-outline{position:sticky;top:24px;max-height:calc(100vh - 48px);border:1px solid #ffffff10;background:#1c1a22;border-radius:14px;display:flex;flex-direction:column;min-height:0;overflow:hidden}.outline-heading{display:flex;justify-content:space-between;gap:10px;padding:18px;font-size:13px;border-bottom:1px solid #ffffff0d}.outline-heading span{color:#928ca3}.lesson-buttons{overflow:auto;padding:8px;scrollbar-width:thin}.lesson-buttons button{display:flex;align-items:baseline;gap:10px;width:100%;text-align:left;font-size:13px;line-height:1.65;background:transparent;padding:12px 10px;border-radius:9px;color:#b6b0c3;overflow-wrap:anywhere}.lesson-buttons button:hover{background:#ffffff05}.lesson-buttons button.chosen{background:#8d78ff20;color:#d7ceff}.lesson-number{color:#8e839e;font-size:11px;font-variant-numeric:tabular-nums;flex-shrink:0}.lesson-content{min-width:0}.lesson-kind,.language-tag{display:inline-block;font-size:11px;border-radius:6px;padding:5px 8px;background:#bca4ff12;color:#c9b7ee;margin:0 8px 14px 0}.language-tag{background:#6ba7b312;color:#99c5ce}.lesson-heading h2{font-size:24px;line-height:1.5;overflow-wrap:anywhere}.lesson-heading p{margin:12px 0 22px}.reading-tabs{display:flex;gap:4px;padding:5px;background:#ffffff05;border-radius:12px;margin-bottom:20px}.reading-tabs button{flex:1;font-size:13px;padding:10px 6px;background:transparent;border-radius:8px;color:#aaa6b8}.reading-tabs button.selected{background:#8470ff28;color:#dbd0ff}.reading-section{padding:22px;border:1px solid #ffffff0d;border-radius:14px;background:#201e27;margin-bottom:18px;overflow:hidden}.reading-section h3{font-size:15px;margin:0 0 16px}.teaching-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;color:#c8c4d1;line-height:1.85}.code-heading{display:flex;justify-content:space-between;gap:12px}.code-heading span{color:#8ed9db;font-size:12px}.reading-section pre{margin:0;background:#15141b;padding:18px;border-radius:10px;overflow:auto;max-height:640px;color:#d4d0e5;line-height:1.7;font-size:12px;tab-size:4}.reading-section code{font-family:ui-monospace,"Cascadia Code",Consolas,monospace}.reading-section h4{font-size:13px;margin:20px 0 10px}.practice{border-color:#9986ff25}.file-chips{display:flex;flex-wrap:wrap;gap:8px}.file-chips code{padding:5px 8px;background:#ffffff05;color:#b9add9;border-radius:6px;font-size:12px;overflow-wrap:anywhere}.practice ol{padding-left:20px;color:#c8c4d1;font-size:14px;line-height:1.8}.practice li+li{margin-top:8px}.read-only-note{font-size:12px;border-top:1px solid #ffffff10;padding-top:16px;margin-bottom:0}.reading-section summary{cursor:pointer;font-size:14px;font-weight:600}.reading-section[open] summary{margin-bottom:18px}.lesson-pagination{display:flex;align-items:center;justify-content:space-between;gap:10px}.lesson-pagination button{padding:10px 14px;background:#8470ff18;border-radius:8px;color:#c3b7ff}.lesson-pagination span{color:#928ca3;font-size:12px}.lesson-pagination button:disabled{cursor:default}.retry{margin-left:12px}.empty{margin-top:12px}@media(max-width:1100px){.reader{grid-template-columns:180px minmax(0,1fr);gap:16px}.reading-section{padding:18px}.course-picker{flex-wrap:wrap}.course-picker>span{display:none}}@media(max-width:850px){.reader{grid-template-columns:1fr}.lesson-outline{position:static;max-height:230px}.lesson-heading h2{font-size:22px}.library-heading{align-items:start}.library-heading .refresh{flex-shrink:0}.loading-grid{grid-template-columns:1fr}.reader-loading{grid-template-columns:1fr}.reader-loading .skeleton:first-child{height:140px}}@media(max-width:580px){.course-picker{display:block}.course-picker label{display:block;margin-bottom:8px}.course-picker select{width:100%;font-size:13px}.reading-section{padding:16px}.library-heading{flex-wrap:wrap}.lesson-pagination button{font-size:12px}}
</style>
