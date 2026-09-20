<script lang="ts">
  import { onMount } from 'svelte';
  import Workspace from './Workspace.svelte';
  import ProfileDashboard from './ProfileDashboard.svelte';
  import SettingsSheet from './SettingsSheet.svelte';
  import CourseBuilder from './CourseBuilder.svelte';
  import SkillLibrary from './SkillLibrary.svelte';
  import PendingInbox from './PendingInbox.svelte';
  import { loadDashboard, loadServiceHealth, type Dashboard } from './gateway';
  let view=$state<'workspace'|'profile'>('workspace');
  let sheet=$state(false);
  let builder=$state<false|'course'|'practice'>(false);
  let library=$state<false|'learn'|'manage'>(false);
  let pending=$state(false);
  let requestedCourse=$state('');
  let profile=$state({name:'学习者',bio:'',avatar:'🧑‍💻'});
  let ready=$state(false);
  let connected=$state(false);
  async function boot(){try{const [data,health]=await Promise.all([loadDashboard(),loadServiceHealth()]);profile={name:data.profile.name,bio:data.profile.bio,avatar:data.profile.avatar};connected=health.ok}catch{connected=false}finally{ready=true}}
  function changed(next:{name:string;bio:string;avatar:string}){profile=next}
  onMount(boot);
</script>
<div class:ready class="app-root">
  {#if view==='profile'}
    <ProfileDashboard onBack={()=>view='workspace'} onSettings={()=>sheet=true} onConnections={()=>sheet=true} onChanged={changed}/>
  {:else}
    <Workspace {profile} {connected} {requestedCourse} onProfile={()=>view='profile'} onSettings={()=>sheet=true} onServices={()=>sheet=true} onBuild={(practice)=>builder=practice?'practice':'course'} onSkills={(mode)=>library=mode} />
  {/if}
  {#if sheet}<SettingsSheet onClose={()=>sheet=false}/>{/if}
  {#if builder}<CourseBuilder practice={builder==='practice'} onClose={()=>builder=false}/>{/if}
  {#if library}<SkillLibrary mode={library} onClose={()=>library=false} onBuild={()=>{library=false;builder='course'}} onPending={()=>{library=false;pending=true}} onCourse={(id)=>{requestedCourse=id;library=false}}/>{/if}
  {#if pending}<PendingInbox onClose={()=>pending=false}/>{/if}
</div>
