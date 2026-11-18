<script>
  import { onMount } from 'svelte';
  import GraphView from './GraphView.svelte';

  let page = $state('chat');
  let question = $state('');
  let text = $state('');
  let messages = $state([]);
  let graph = $state({ nodes: [], edges: [] });
  let documents = $state([]);
  let notice = $state('');
  let isSubmitting = $state(false);

  async function loadDocuments() {
    const response = await fetch('/api/episodes');
    documents = await response.json();
  }

  onMount(() => {
    loadDocuments();
    const timer = setInterval(() => {
      if (documents.some((document) => document.status === 'queued' || document.status === 'processing')) {
        loadDocuments();
      }
    }, 2000);
    return () => clearInterval(timer);
  });

  async function sendMessage() {
    const prompt = question;
    messages.push({ role: 'user', text: prompt });
    question = '';
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: prompt }),
    });
    const result = await response.json();
    graph = result;
    messages.push({ role: 'assistant', text: result.answer });
  }

  async function ingest() {
    isSubmitting = true;
    notice = '登録をキューに追加しています…';
    try {
      const response = await fetch('/api/episodes', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(`API error: ${response.status}`);
      text = '';
      notice = 'バックグラウンド登録を開始しました';
      await loadDocuments();
    } catch (error) {
      notice = `登録を開始できませんでした: ${error.message}`;
    } finally {
      isSubmitting = false;
    }
  }

  async function deleteDocument(document) {
    const response = await fetch(`/api/episodes/${document.id}`, { method: 'DELETE' });
    const result = await response.json();
    if (result.status === 'deleted') {
      notice = 'ドキュメントを削除しました';
      await loadDocuments();
    } else {
      notice = '登録処理中のドキュメントは削除できません';
    }
  }

  function statusLabel(status) {
    return { queued: '待機中', processing: '登録中', completed: '登録済み', failed: '失敗' }[status] ?? status;
  }
</script>

<svelte:head><title>Graphiti Sample</title></svelte:head>

<header>
  <strong>Graphiti Sample</strong>
  <nav>
    <button class:active={page === 'chat'} onclick={() => page = 'chat'}>チャット</button>
    <button class:active={page === 'ingest'} onclick={() => page = 'ingest'}>データ投入</button>
  </nav>
</header>

{#if page === 'chat'}
  <main class="chat-layout">
    <section class="conversation">
      <div class="messages">
        {#each messages as message}
          <article class:user={message.role === 'user'}>
            <small>{message.role === 'user' ? 'あなた' : 'Graphiti'}</small>
            <p>{message.text}</p>
          </article>
        {/each}
      </div>
      <form onsubmit={(event) => { event.preventDefault(); sendMessage(); }}>
        <input bind:value={question} placeholder="グラフに質問する" />
        <button class="primary">送信</button>
      </form>
    </section>
    <section class="graph-panel">
      <h2>検索コンテキスト</h2>
      {#if graph.nodes.length}
        <GraphView {graph} />
      {:else}
        <p class="empty">質問を送ると、関連するノードと関係がここに表示されます。</p>
      {/if}
    </section>
  </main>
{:else}
  <main class="documents-page">
    <section class="ingest-panel">
      <h1>データ投入</h1>
      <p>テキストを入力すると、バックグラウンドで Graphiti に登録します。</p>
      <form onsubmit={(event) => { event.preventDefault(); ingest(); }}>
        <textarea bind:value={text} rows="8" placeholder="登録するドキュメント本文"></textarea>
        <button class="primary" disabled={isSubmitting}>
          {isSubmitting ? '送信中…' : 'Graphiti に登録'}
        </button>
      </form>
      {#if notice}<p class="notice">{notice}</p>{/if}
    </section>

    <section class="documents-panel">
      <h2>ドキュメント一覧</h2>
      {#if documents.length}
        <ul class="document-list">
          {#each documents as document (document.id)}
            <li>
              <div>
                <strong>{document.title}</strong>
                <small>{new Date(document.created_at).toLocaleString()}</small>
              </div>
              <span class="status" class:failed={document.status === 'failed'}>{statusLabel(document.status)}</span>
              <button
                class="delete-button"
                disabled={document.status === 'queued' || document.status === 'processing'}
                onclick={() => deleteDocument(document)}
              >削除</button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty">登録されたドキュメントはありません。</p>
      {/if}
    </section>
  </main>
{/if}
