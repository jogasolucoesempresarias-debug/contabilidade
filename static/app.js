// Portal Contábil — utilidades comuns às páginas.
const MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const SITUACAO = {
  sem_envio: 'Sem envio', recebendo: 'Recebendo', pendencia: 'Com pendência', pronta: 'Pronta', baixada: 'Baixada',
};

async function api(url, opts = {}) {
  const r = await fetch(url, { credentials: 'same-origin', ...opts });
  let corpo = {};
  try { corpo = await r.json(); } catch (_) { /* resposta sem JSON */ }
  if (r.status === 401) { location.href = '/login'; throw new Error(corpo.error || 'Sessão expirada'); }
  if (r.status === 403 && corpo.redirect) { location.href = corpo.redirect; throw new Error(corpo.error); }
  if (!r.ok || corpo.ok === false) throw new Error(corpo.error || `Erro ${r.status}`);
  return corpo;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function brl(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function dataBR(iso) {
  if (!iso) return '';
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}

function dataHoraBR(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

function mesExtenso(mes) {
  const [a, m] = mes.split('-').map(Number);
  return `${MESES[m - 1]}/${a}`;
}

function mesDeslocado(mes, delta) {
  let [a, m] = mes.split('-').map(Number);
  m += delta;
  while (m < 1) { m += 12; a -= 1; }
  while (m > 12) { m -= 12; a += 1; }
  return `${a}-${String(m).padStart(2, '0')}`;
}

function pill(situacao, texto) {
  return `<span class="pill s-${esc(situacao)}">${esc(texto || SITUACAO[situacao] || situacao)}</span>`;
}

function toast(msg) {
  const t = document.createElement('div');
  t.className = 'toast'; t.textContent = msg; t.setAttribute('role', 'status');
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

function aplicarTema() {
  try { const t = localStorage.getItem('tema'); if (t) document.documentElement.dataset.tema = t; } catch (_) { /* sem storage */ }
}
function alternarTema() {
  const escuroAgora = document.documentElement.dataset.tema
    ? document.documentElement.dataset.tema === 'escuro'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  const novo = escuroAgora ? 'claro' : 'escuro';
  document.documentElement.dataset.tema = novo;
  try { localStorage.setItem('tema', novo); } catch (_) { /* sem storage */ }
}
aplicarTema();

// Cabeçalho comum: marca, navegação, usuário, faixa da demonstração.
async function montarTopo(ativo) {
  const [marca, me] = await Promise.all([api('/api/marca'), api('/api/me').catch(() => null)]);
  document.title = `${document.title} · ${marca.nome}`;
  const iniciais = marca.nome.split(/\s+/).filter(Boolean).slice(0, 2).map(p => p[0]).join('').toUpperCase();
  const topo = document.createElement('header');
  topo.innerHTML = `
    <div class="topo"><div class="topo-in">
      <div class="marca"><span class="marca-selo" aria-hidden="true">${esc(iniciais)}</span><span class="marca-nome">${esc(marca.nome)}</span></div>
      <nav class="nav">
        <a href="/clientes" class="${ativo === 'clientes' ? 'ativo' : ''}">Clientes</a>
        <a href="/regras" class="${ativo === 'regras' ? 'ativo' : ''}">Regras</a>
      </nav>
      <div class="topo-dir">
        <button class="btn-texto" id="btn-tema" type="button" title="Alternar tema claro/escuro">◐</button>
        <span>${esc(me ? me.nome : '')}</span>
        <a class="btn-texto" href="/logout">Sair</a>
      </div>
    </div></div>
    ${marca.aviso ? `<div class="aviso-demo"><div>ⓘ ${esc(marca.aviso)}</div></div>` : ''}`;
  document.body.prepend(topo);
  document.getElementById('btn-tema').onclick = alternarTema;
  return { marca, me };
}
