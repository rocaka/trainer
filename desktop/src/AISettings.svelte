<script lang="ts">
  import { onMount } from 'svelte';
  import { invoke, isTauri } from '@tauri-apps/api/core';

  interface Runtime {
    owned: boolean;
    isolated: boolean;
    settingsWritable: boolean;
  }
  interface Settings {
    enabled: boolean;
    endpoint: string;
    model: string;
    protocol: 'chat-completions' | 'responses';
    hasKey: boolean;
  }

  let runtime = $state<Runtime | null>(null);
  let settings = $state<Settings | null>(null);
  let endpoint = $state('');
  let model = $state('');
  let protocol = $state<Settings['protocol']>('chat-completions');
  let secret = $state('');
  let consent = $state(false);
  let loading = $state(true);
  let saving = $state(false);
  let error = $state('');
  let success = $state('');
  let browserPreview = $state(false);
  let alive = true;
  const writable = $derived(runtime?.owned === true && runtime.settingsWritable === true);

  function checkedRuntime(value: Runtime): Runtime {
    if (typeof value?.owned !== 'boolean' || typeof value.isolated !== 'boolean' ||
        typeof value.settingsWritable !== 'boolean') throw new Error('运行状态格式不兼容');
    return value;
  }

  function checkedSettings(value: Settings): Settings {
    if (typeof value?.enabled !== 'boolean' || typeof value.endpoint !== 'string' ||
        typeof value.model !== 'string' || typeof value.hasKey !== 'boolean' ||
        !['chat-completions', 'responses'].includes(value.protocol)) {
      throw new Error('设置格式不兼容');
    }
    return value;
  }

  function applySettings(value: Settings) {
    settings = value;
    endpoint = value.endpoint;
    model = value.model;
    protocol = value.protocol;
  }

  async function load() {
    if (saving) return;
    loading = true;
    error = '';
    success = '';
    secret = '';
    consent = false;
    runtime = null;
    settings = null;
    browserPreview = !isTauri();
    if (browserPreview) {
      loading = false;
      return;
    }
    try {
      const current = checkedRuntime(await invoke<Runtime>('desktop_runtime'));
      if (!alive) return;
      runtime = current;
      if (current.owned) {
        const value = checkedSettings(await invoke<Settings>('ai_settings'));
        if (alive) applySettings(value);
      }
    } catch {
      // Native failures must not echo a request body or supplied secret.
      if (alive) {
        runtime = null;
        error = '无法读取 AI 服务设置。请检查桌面后端是否已启动，然后重试。';
      }
    } finally {
      if (alive) loading = false;
    }
  }

  function validate(): string {
    if (!consent) return '请先确认下方的材料发送授权。';
    if (!endpoint.trim() || endpoint.trim().length > 2048) return '请填写有效的服务地址。';
    try {
      const address = new URL(endpoint.trim());
      const local = ['localhost', '127.0.0.1', '[::1]'].includes(address.hostname);
      if (!address.hostname || (address.protocol !== 'https:' && !(address.protocol === 'http:' && local)) ||
          address.username || address.password || address.search || address.hash) {
        return '服务地址需使用 HTTPS；本机服务可使用 HTTP。地址中不能包含密钥、账户、查询参数或片段。';
      }
    } catch {
      return '服务地址格式不正确，请包含 https:// 或本机服务的 http://。';
    }
    if (!model.trim() || model.trim().length > 200) return '请填写服务商提供的模型名称，长度不超过 200 个字符。';
    if (secret.includes('\0') || new TextEncoder().encode(secret).length > 2560) return '密钥格式或长度不符合系统凭据要求。';
    if (!secret && !settings?.hasKey) return '此服务尚未保存密钥，请填写 API 密钥。';
    return '';
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    if (saving || loading || !writable) return;
    success = '';
    error = validate();
    if (error) return;
    saving = true;
    try {
      // Recheck backend ownership before sending any secret to the native bridge.
      const current = checkedRuntime(await invoke<Runtime>('desktop_runtime'));
      if (!alive) return;
      runtime = current;
      if (!current.owned || !current.settingsWritable) {
        secret = '';
        consent = false;
        error = '当前运行环境不允许修改凭据，未发送密钥。';
        return;
      }
      const result = await invoke<{ saved: boolean; settings: Settings }>('save_ai_settings', {
        settings: { endpoint: endpoint.trim(), model: model.trim(), protocol, secret, consent }
      });
      if (!alive) return;
      // Clear even if the post-save response format is unexpected.
      secret = '';
      consent = false;
      if (result?.saved !== true) throw new Error('保存状态不兼容');
      applySettings(checkedSettings(result.settings));
      success = '已保存并启用。尚未进行模型连接测试，本次没有发送课程或项目材料。';
    } catch {
      if (alive) {
        secret = '';
        consent = false;
        error = '未能确认保存成功。请重新读取设置；检查服务地址、模型名称和系统凭据权限后再试。';
      }
    } finally {
      if (alive) saving = false;
    }
  }

  onMount(() => {
    alive = true;
    void load();
    return () => { alive = false; secret = ''; consent = false; };
  });
</script>

<section class="panel ai-settings" aria-labelledby="ai-settings-title" aria-busy={loading || saving}>
  <div class="section-heading">
    <div><h3 id="ai-settings-title">AI 服务配置</h3><p class="muted intro">连接你选择的模型服务，密钥仅由本机系统凭据管理。</p></div>
    <button class="refresh" type="button" disabled={loading || saving} onclick={load}>{loading ? '读取中…' : '重新读取'}</button>
  </div>

  {#if loading}
    <div class="settings-skeleton" aria-label="正在读取 AI 设置"><span></span><span></span><span></span></div>
  {:else}
    {#if error}<div class="notice" role="alert">{error}</div>{/if}
    {#if success}<div class="notice saved" role="status">{success}</div>{/if}

    {#if browserPreview}
      <div class="notice">当前是浏览器界面预览，不会读取或保存密钥。请在桌面客户端配置 AI 服务。</div>
    {:else if !writable}
      <div class="notice" role="status">
        {#if runtime?.isolated}
          当前为隔离预览，不读取或修改你已有的系统密钥。凭据配置保持关闭，不影响 Mac 原版 Trainer。
        {:else}
          当前连接为只读模式，不能修改现有服务或接收密钥。Mac 用户请在原版 Trainer 的「AI 服务」中管理配置。
        {/if}
      </div>
      {#if settings}
        <dl class="settings-summary">
          <div><dt>服务状态</dt><dd>{settings.enabled ? '已启用' : '尚未启用'}</dd></div>
          <div><dt>模型</dt><dd>{settings.model || '尚未配置'}</dd></div>
          <div><dt>密钥状态</dt><dd>{settings.hasKey ? '已有凭据 · 不展示内容' : '未检测到凭据'}</dd></div>
        </dl>
      {/if}
    {:else}
      <form onsubmit={save} autocomplete="off">
        <fieldset disabled={saving}>
          <div class="field-row">
            <label for="ai-protocol">接口协议<select id="ai-protocol" bind:value={protocol}><option value="chat-completions">聊天补全（Chat Completions）</option><option value="responses">响应接口（Responses）</option></select></label>
            <label for="ai-model">模型名称<input id="ai-model" type="text" bind:value={model} maxlength="200" required placeholder="填写服务商提供的精确模型名称" spellcheck="false" /></label>
          </div>
          <label for="ai-endpoint">服务地址<input id="ai-endpoint" type="url" bind:value={endpoint} maxlength="2048" required placeholder="https://你的服务地址/v1" spellcheck="false" /></label>
          <p class="field-help muted">可填写基础地址或完整接口路径；密钥请填写在下方，不要放进地址。</p>
          <label for="ai-secret">{settings?.hasKey ? '更新 API 密钥（可选）' : 'API 密钥'}<input id="ai-secret" type="password" bind:value={secret} maxlength="2560" autocomplete="new-password" placeholder={settings?.hasKey ? '留空保留此服务已有的密钥' : '输入密钥，仅保存到系统凭据'} spellcheck="false" /></label>
          <p class="field-help muted">密钥不会显示、写入浏览器存储或随学习数据同步。更换服务地址时，可能需要重新提供密钥。</p>
          <label class="consent" for="ai-consent"><input id="ai-consent" type="checkbox" bind:checked={consent} /><span>我允许 Trainer 在我使用 AI 功能时，将课程、回答及已授权的项目材料发送到此服务。</span></label>
          <div class="settings-actions"><button class="refresh save" type="submit" disabled={!consent}>{saving ? '正在安全保存…' : '保存并启用'}</button><span class="muted">只保存配置，不自动调用模型。</span></div>
        </fieldset>
      </form>
    {/if}
    <p class="footnote muted">已保存凭据不代表连接、余额或模型权限已通过验证。每台设备独立配置密钥。</p>
  {/if}
</section>

<style>
  .ai-settings { margin-top: 20px; }
  .section-heading { align-items: flex-start; }
  .section-heading > div { min-width: 0; }
  .intro { margin: 8px 0 0; }
  .section-heading > button { flex-shrink: 0; }
  fieldset { border: 0; padding: 0; margin: 0; min-width: 0; }
  label { display: grid; gap: 9px; font-size: 14px; color: #ded9eb; margin-top: 18px; }
  input:not([type='checkbox']), select { display: block; width: 100%; min-width: 0; border: 1px solid #ffffff20; border-radius: 10px; padding: 12px; background: #17151e; color: inherit; font: inherit; }
  input:focus-visible, select:focus-visible { outline: 2px solid #9c91ff; outline-offset: 3px; }
  input:disabled, select:disabled { opacity: .6; }
  input::placeholder { color: #9690a5; }
  .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .field-help { margin: 8px 0 0; font-size: 12px; }
  .consent { grid-template-columns: 18px minmax(0, 1fr); align-items: start; gap: 12px; line-height: 1.65; margin-top: 24px; }
  .consent input { width: 18px; height: 18px; margin: 3px 0 0; accent-color: #9986ff; }
  .settings-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; margin-top: 24px; }
  .save { background: #7964ff; color: white; }
  .save:disabled { cursor: not-allowed; }
  .settings-actions span, .footnote { font-size: 12px; }
  .footnote { margin: 22px 0 0; padding-top: 16px; border-top: 1px solid #ffffff0d; }
  .saved { color: #a9d9c8; border-color: #81c6ae40; background: #81c6ae0a; }
  .settings-summary { margin: 20px 0 0; display: grid; gap: 12px; font-size: 14px; }
  .settings-summary > div { display: flex; justify-content: space-between; gap: 20px; }
  dt { color: #aaa6b8; }
  dd { margin: 0; text-align: right; overflow-wrap: anywhere; }
  .settings-skeleton { display: grid; gap: 16px; padding-top: 10px; }
  .settings-skeleton span { height: 44px; border-radius: 10px; background: #ffffff08; }
  @media (max-width: 760px) { .field-row { grid-template-columns: 1fr; gap: 0; } }
  @media (max-width: 480px) { .section-heading { flex-wrap: wrap; } }
</style>
