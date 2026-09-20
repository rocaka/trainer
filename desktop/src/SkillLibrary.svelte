<script lang="ts">
  import { onMount } from 'svelte';
  import { trainerAction } from './gateway';

  type Skill={id:string;title:string;status:string;version:string;languages:string[];category?:string};
  let {mode,onClose,onBuild,onPending,onCourse}=$props<{mode:'learn'|'manage';onClose:()=>void;onBuild:()=>void;onPending:()=>void;onCourse:(id:string)=>void}>();
  let skills=$state<Skill[]>([]);let selected=$state<Skill|null>(null);let detail=$state<Record<string,unknown>|null>(null);
  let loading=$state(true);let planning=$state(false);let progress=$state(0);let stage=$state('');let error=$state('');
  const groups=$derived([
    {key:'project-practice',title:'项目实战',items:skills.filter(x=>x.category==='project-practice')},
    {key:'course',title:'课程教学',items:skills.filter(x=>x.status!=='core'&&x.category!=='project-practice')},
    {key:'core',title:'核心教学规则',items:skills.filter(x=>x.status==='core')}
  ].filter(x=>x.items.length));
  const message=(e:unknown)=>e instanceof Error?e.message:String(e);
  async function load(){loading=true;error='';try{const value=await trainerAction<{skills:Skill[]}>('skills');skills=value.skills??[];if(skills.length&&!selected)await choose(skills[0])}catch(e){error=message(e)}finally{loading=false}}
  async function choose(skill:Skill){selected=skill;detail=null;try{detail=await trainerAction<Record<string,unknown>>('skill-detail',{id:skill.id})}catch{detail=null}}
  async function start(){if(!selected||planning)return;planning=true;error='';progress=8;stage='正在读取本地课程与教学上下文…';try{const first=await trainerAction<{id:string}>('plan-generate',{skillId:selected.id,mode:'open',planId:''});for(let i=0;i<900;i++){await new Promise(r=>setTimeout(r,1000));const job=await trainerAction<Record<string,unknown>>('job',{id:first.id});stage=String(job.message??'正在展开课程…');progress=Number(job.total)?Math.max(8,Math.min(96,Number(job.completed??0)/Number(job.total)*100)):Math.min(94,progress+1.5);const result=(job.result??job.partialResult) as Record<string,unknown>|undefined;if(job.status==='completed'&&result){const id=String(result.planId??result.id??'');if(!id)throw new Error('课程已生成，但返回的课程编号无效。');progress=100;stage='课程已准备好';setTimeout(()=>onCourse(id),320);return}if(['failed','paused','cancelled'].includes(String(job.status)))throw new Error(String(job.error??'课程生成未完成，可在任务中心继续。'))}throw new Error('课程仍在生成，可在任务中心查看进度。')}catch(e){error=message(e)}finally{planning=false}}
  function documents(){const value=detail?.documents;return value&&typeof value==='object'?Object.entries(value as Record<string,string>):[]}
  onMount(load);
</script>

<div class="modal-backdrop" onclick={(e)=>{if(e.target===e.currentTarget)onClose()}} role="presentation">
  <div class="library-window modal-enter" role="dialog" aria-modal="true">
    <header class="library-header"><div><span class="eyebrow">TRAINER KNOWLEDGE</span><h1>{mode==='learn'?'选择教学方向':'Skill 知识库'}</h1><p>{mode==='learn'?'从任意 Skill 开始，Trainer 自动衔接必要基础。':'Skill 是可审计的教学协议；候选内容审批后才进入可信课程。'}</p></div><div class="header-actions">{#if mode==='manage'}<button onclick={onPending}>待审批</button><button class="primary" onclick={onBuild}>生成候选 Skill</button>{/if}<button class="close-button" onclick={onClose}>完成</button></div></header>
    {#if error}<div class="notice">{error}</div>{/if}
    {#if planning}<div class="planning-strip"><span class="spinner"></span><div><strong>{stage}</strong><div class="fluid-track"><i style={`width:${progress}%`}></i></div></div><b>{Math.round(progress)}%</b></div>{/if}
    <div class="library-body">
      <aside class="skill-index">
        {#if loading}<div class="skeleton-stack"><i></i><i></i><i></i><i></i></div>{/if}
        {#each groups as group}<section><h2>{group.title}</h2>{#each group.items as skill}<button class:active={selected?.id===skill.id} onclick={()=>choose(skill)}><span class="skill-icon">{skill.category==='project-practice'?'⚒':skill.status==='core'?'◇':'▤'}</span><span><strong>{skill.title}</strong><small>{skill.languages?.join(' · ')||'通用能力'} · {skill.status}</small></span><b>›</b></button>{/each}</section>{/each}
      </aside>
      <main class="skill-preview">
        {#if selected}<div class="skill-title"><div><span class="badge">{selected.category==='project-practice'?'项目实战':selected.status==='core'?'核心规则':'课程教学'}</span><h2>{selected.title}</h2><p>{selected.id} · v{selected.version}</p></div>{#if mode==='learn'&&selected.status!=='core'}<button class="primary start-course" onclick={start} disabled={planning}>开始学习 <span>→</span></button>{/if}</div>
          {#if detail}<div class="rule-card"><strong>教学资产已验证</strong><span>{String((detail.ruleStatus as Record<string,unknown>)?.message??'课程规则与版本可追溯。')}</span></div>{#each documents().slice(0,3) as [name,text]}<article class="document-preview"><h3>{name}</h3><p>{text.slice(0,680)}</p></article>{/each}{:else}<div class="preview-skeleton"><i></i><i></i><i></i><i></i></div>{/if}
        {:else if !loading}<div class="empty-compact">知识库中还没有可用 Skill</div>{/if}
      </main>
    </div>
  </div>
</div>
