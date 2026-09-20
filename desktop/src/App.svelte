<script lang="ts">
  import { onMount } from 'svelte';
  import AISettings from './AISettings.svelte';
  import CourseLibrary from './CourseLibrary.svelte';
  import { loadDashboard, loadServiceHealth, runtimeStatus, restartPreview, type Dashboard, type ServiceHealth } from './gateway';
  let health = $state<ServiceHealth | null>(null);
  let healthBusy = $state(false);
  let healthError = $state('');
  async function checkHealth() {
    if (healthBusy) return;
    healthBusy = true; healthError = ''; health = null;
    try { health = await loadServiceHealth(); }
    catch (e) { healthError = e instanceof Error ? e.message : String(e); }
    finally { healthBusy = false; }
  }
  let runtime = $state('正在检查本地服务…');
  async function startBackend() {
    try { await restartPreview(); runtime = await runtimeStatus(); error = '后端启动中，请稍后刷新档案。'; }
    catch (e) { error = e instanceof Error ? e.message : String(e); }
  }
  let data = $state<Dashboard | null>(null);
  let busy = $state(false);
  let error = $state('');
  let page = $state<'profile' | 'progress' | 'settings' | 'courses'>('profile');
  const milestones = [
    ['桌面基础', 'Tauri + Svelte 客户端、响应式界面和减少动态效果', true],
    ['本地档案', '只读接入现有 Gateway，不复制或修改 Mac 数据', true],
    ['独立运行', '进行中：启动清理、打包脚本与系统凭据适配已实现；待 Windows 文件权限与实机验收', false],
    ['课程与提交', '课程阅读已实现；工作区关联、提交检查与 AI 评判待接入', false],
    ['账户与同步', '同一账户跨设备同步、冲突处理与离线恢复', false],
    ['发布验收', 'Windows 实机测试、签名安装与更新', false],
  ] as const;
  async function refresh() {
    if (busy) return;
    busy = true; error = '';
    try { data = await loadDashboard(); } catch (e) { error = e instanceof Error ? e.message : String(e); }
    finally { busy = false; runtime = await runtimeStatus().catch(() => '运行状态暂不可用'); }
  }
  onMount(refresh);
</script>

<div class="shell">
  <aside>
    <div class="brand"><span class="mark">T</span> Trainer</div>
    <p class="muted">你的 AI 技术导师</p>
    <nav aria-label="主导航">
      <button class:active={page === 'profile'} onclick={() => page = 'profile'}>个人空间 <span>↗</span></button>
      <button class:active={page === 'courses'} onclick={() => page = 'courses'}>课程学习 <span>→</span></button>
      <button class:active={page === 'progress'} onclick={() => page = 'progress'}>开发进度 <span>2 / 6</span></button>
      <button class:active={page === 'settings'} onclick={() => { page = 'settings'; checkHealth(); }}>服务设置 <span>⚙</span></button>
    </nav>
    <div class="side-note">跨平台预览版 <small>{runtime}</small></div>
  </aside>
  <main>
    <header><div><p class="eyebrow">YOUR LEARNING SPACE</p><h1>{page === 'profile' ? '个人空间' : page === 'settings' ? '服务设置' : page === 'courses' ? '课程学习' : '跨平台开发进度'}</h1></div><span class="badge">早期预览</span></header>
    {#if page === 'courses'}
      <CourseLibrary />
    {:else if page === 'settings'}
      <section class="hero"><p class="eyebrow">LOCAL SERVICE</p><h2>连接状态，一目了然。</h2><p>检查本地后端、AI 配置和提交能力。此操作不会调用模型或产生模型费用。</p></section>
      <div class="section-heading"><h2>运行检查</h2><button class="refresh" disabled={healthBusy} onclick={checkHealth}>{healthBusy ? '检查中…' : '重新检查'}</button></div>
      {#if healthBusy}<div class="panel skeleton" aria-label="正在检查服务" aria-busy="true"></div>
      {:else if healthError}<div class="notice" role="status">{healthError}</div>
      {:else if health}
        <div class="milestones">
          <section class="panel"><h3>本地 Gateway · {health.ok ? '在线' : '未就绪'}</h3><p>仅连接本机，不开放远程访问。</p></section>
          <section class="panel"><h3>AI 服务 · {health.configured ? '已检测到凭据' : '未配置凭据'}</h3><p>{health.provider} · {health.model}</p><small class="muted">检测到凭据不代表余额、模型权限或网络测试已通过。</small></section>
          <section class="panel"><h3>代码提交 · {health.submissionReady === true ? '本地存储已就绪' : '尚未就绪'}</h3><p>{health.secureSubmissionSupported === false ? '当前平台安全文件读取尚未适配，提交保持禁用。' : health.secureSubmissionSupported === true ? '平台支持安全读取；实际提交仍需课程关联、文件授权和 AI 服务。' : '此 Gateway 未报告安全能力，请更新后再检查。'}</p></section>
        </div>
      {/if}
      <div style="margin-top:20px"><AISettings /></div>
    {:else if page === 'progress'}
      <section class="hero"><p class="eyebrow">BUILDING TRAINER</p><h2>一套学习数据，两个桌面。</h2><p>先复用现有业务核心，再逐步接通课程与同步。这里显示里程碑，不代表整体验收完成率。</p></section>
      <div class="milestones">{#each milestones as [name, detail, done], i}<section class="panel step"><span class:done class="step-number">{done ? '✓' : i + 1}</span><div><h3>{name}</h3><p>{detail}</p></div><span class="muted">{done ? '已实现 · 待跨平台验收' : '待完成'}</span></section>{/each}</div>
    {:else}
      <section class="hero"><p class="eyebrow">保持好奇，持续生长</p><h2>{data?.profile.name ?? '欢迎回到 Trainer'}</h2><p>{data?.profile.bio || '让每一次练习，都成为可见的成长。'}</p></section>
      <div class="section-heading"><h2>学习概览</h2><button class="refresh" disabled={busy} onclick={refresh}>{busy ? '正在读取…' : '刷新档案'}</button></div>
      {#if error}<div class="notice" role="status">{error}{#if data}<br/>下方保留上次读取的数据。{/if}</div>{/if}
      {#if busy && !data}<div class="stats" aria-label="正在加载档案" aria-busy="true">{#each [1,2,3] as n}<div class="panel skeleton"></div>{/each}</div>
      {:else if data}
        <div class="stats"><section class="panel"><p>课堂凭据</p><strong>{data.evidenceCount}</strong></section><section class="panel"><p>活跃天数</p><strong>{data.activeDays}</strong></section><section class="panel"><p>连续学习</p><strong>{data.currentStreak}<small> 天</small></strong></section></div>
        <div class="section-heading"><h2>语言档案</h2><span class="muted">{data.languages.length} 种语言</span></div>
        <p class="muted">课堂评分与 GitHub 项目接触面分开记录。</p>
        <div class="languages">{#each data.languages as language (language.name)}<section class="panel language"><div class="section-heading"><h3>{language.name}</h3><span class="score">{language.score == null ? '未评估' : `${language.score} / 100`}</span></div>{#if language.score != null}<progress max="100" value={language.score} aria-label={`${language.name} 课堂评分`}></progress>{/if}<p>{language.evidenceCount} 条课堂凭据</p><small class="github">{language.githubBytes > 0 ? `GitHub · ${language.githubRepositoryCount} 个项目 · ${Math.ceil(language.githubBytes / 1024)} KB` : '暂无 GitHub 数据'}</small></section>{:else}<p class="muted">完成练习或同步 GitHub 后，语言档案会显示在这里。</p>{/each}</div>
      {:else}<section class="panel empty"><h3>档案尚未连接</h3><p>默认连接现有服务；隔离开发模式使用临时数据，不会覆盖你的学习记录。</p><button class="refresh" onclick={startBackend}>重试启动本地后端</button></section>{/if}
    {/if}
  </main>
</div>
