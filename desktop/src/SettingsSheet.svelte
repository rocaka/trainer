<script lang="ts">
  import { onMount } from 'svelte';
  import AISettings from './AISettings.svelte';
  import { loadServiceHealth, runtimeStatus, trainerAction, type ServiceHealth } from './gateway';
  let { onClose }=$props<{onClose:()=>void}>();
  let tab=$state<'service'|'account'|'connections'|'tasks'|'appearance'>('service'); let health=$state<ServiceHealth|null>(null); let runtime=$state('');let error=$state('');let busy=$state(false);let account=$state<Record<string,unknown>|null>(null);let jobs=$state<Record<string,unknown>[]>([]);
  async function load(){busy=true;error='';try{[health,runtime]=await Promise.all([loadServiceHealth(),runtimeStatus()]);account=await trainerAction<Record<string,unknown>>('account').catch(()=>null);const value=await trainerAction<{jobs:Record<string,unknown>[]}>('jobs').catch(()=>({jobs:[]}));jobs=value.jobs??[]}catch(e){error=e instanceof Error?e.message:String(e)}finally{busy=false}}
  async function sync(){busy=true;error='';try{account=await trainerAction<Record<string,unknown>>('account-sync',{})}catch(e){error=e instanceof Error?e.message:String(e)}finally{busy=false}}
  onMount(load);
</script>
<div class="modal-backdrop" role="presentation" onclick={(e)=>{if(e.target===e.currentTarget)onClose()}}>
  <div class="settings-window" role="dialog" aria-modal="true" aria-label="Trainer 设置">
    <aside class="settings-nav"><h2>Trainer 设置</h2>{#each [['service','AI 服务','✦'],['account','账户与同步','◎'],['connections','连接管理','⌁'],['tasks','生成任务','◷'],['appearance','外观与动效','◐']] as [key,label,icon]}<button class:active={tab===key} onclick={()=>tab=key as typeof tab}><span>{icon}</span>{label}</button>{/each}<span class="settings-version">Windows 预览版 · 0.1.0</span></aside>
    <main class="settings-main"><header><div><h1>{tab==='service'?'Trainer AI 服务':tab==='account'?'账户与跨设备同步':tab==='connections'?'连接 VS Code':tab==='tasks'?'生成任务':'外观与动效'}</h1><p>{tab==='service'?'每位用户配置自己的模型服务与密钥。':tab==='account'?'课程和进度进入云端；密钥与本机路径不参与同步。':tab==='connections'?'关联工作区、检查授权和连接状态。':tab==='tasks'?'查看课程与候选教学的后台生成进度。':'保持 Mac 与 Windows 一致的深色玻璃体验。'}</p></div><button class="close-button" onclick={onClose}>完成</button></header>
      {#if error}<div class="notice">{error}</div>{/if}
      {#if tab==='service'}<div class="health-strip"><span class:online={health?.ok}>● {health?.ok?'本地 Gateway 在线':'本地服务未就绪'}</span><span>{health?.configured?'AI 凭据已配置':'尚未配置 AI 凭据'}</span><span>{runtime}</span><button onclick={load} disabled={busy}>↻ 检查</button></div><AISettings/>
      {:else if tab==='account'}<div class="settings-card"><h3>同步状态</h3><p>{account?JSON.stringify(account):'尚未登录可部署账户服务。'}</p><button class="primary" onclick={sync} disabled={busy}>立即同步</button></div><div class="settings-card"><h3>跨设备原则</h3><p>同步课程、进度、档案与冲突记录；API Key、GitHub Token、工作区路径和本机授权始终留在各自设备。</p></div>
      {:else if tab==='connections'}<div class="settings-card status-list"><div><span class="status-dot"></span><p><strong>本地 Trainer</strong><small>{health?.ok?'连接有效':'等待后台'}</small></p><button onclick={load}>刷新</button></div><div><span>◌</span><p><strong>VS Code 工作区</strong><small>Windows 安全文件授权仍在适配，代码提交保持禁用。</small></p><button disabled>关联工作区</button></div><div><span>⌁</span><p><strong>GitHub</strong><small>登录与仓库语言同步由账户连接管理。</small></p><button disabled>管理授权</button></div></div>
      {:else if tab==='tasks'}<div class="task-list">{#each jobs as job}<article class="settings-card"><div><strong>{String(job.status??'unknown')}</strong><span>{String(job.message??job.id??'生成任务')}</span></div><progress max={Number(job.total??1)} value={Number(job.completed??0)}></progress></article>{:else}<div class="empty-compact">暂无生成任务</div>{/each}</div>
      {:else}<div class="settings-card"><h3>显示</h3><label class="setting-row"><span><strong>深色玻璃</strong><small>与 Mac 工作台保持一致</small></span><input type="checkbox" checked disabled/></label><label class="setting-row"><span><strong>动态效果</strong><small>遵循 Windows 系统“减少动画”设置</small></span><input type="checkbox" checked/></label></div>{/if}
    </main>
  </div>
</div>
