'use client'

import { useState } from 'react'
import {
  Archive, ArrowDownToLine, BarChart3, Bell, Bot, ChevronRight, CircleHelp,
  ClipboardList, Database, LayoutDashboard, Package, Plus, Search, Settings,
  ShieldCheck, ShoppingBag, Store, Users, Wallet, X
} from 'lucide-react'

const modules = [
  { name: 'Visão geral', icon: LayoutDashboard },
  { name: 'Boas-vindas', icon: Bell },
  { name: 'Registro', icon: ClipboardList },
  { name: 'Vendas', icon: ShoppingBag },
  { name: 'Banco', icon: Wallet },
  { name: 'Farm', icon: Package },
  { name: 'Hierarquia', icon: Users },
  { name: 'Ausências', icon: Archive },
]

const activity = [
  ['Registro aprovado', 'matheus.s entrou para a organização', 'Agora'],
  ['Venda registrada', 'AK-47 • R$ 8.500,00', 'há 12 min'],
  ['Farm enviado', 'bruno_r enviou 120 unidades', 'há 28 min'],
  ['Ausência solicitada', 'luiszin pediu 3 dias', 'há 1 h'],
]

export function ImpuneDashboard() {
  const [active, setActive] = useState('Visão geral')
  const [showModal, setShowModal] = useState(false)
  const [search, setSearch] = useState('')

  return (
    <main className="min-h-screen bg-[#0b0909] text-[#f4eee8] selection:bg-orange-500/30">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[248px] border-r border-white/[.07] bg-[#100d0c] lg:block">
        <div className="flex h-full flex-col px-4 py-5">
          <div className="mb-8 flex items-center gap-3 px-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-[#f15a24] shadow-[0_0_24px_rgba(241,90,36,.25)]"><Bot size={21} /></div>
            <div><p className="text-sm font-bold tracking-[.18em]">IMPUNE</p><p className="text-[10px] uppercase tracking-widest text-white/40">Central de gestão</p></div>
          </div>
          <p className="mb-3 px-3 text-[10px] font-semibold uppercase tracking-[.2em] text-white/30">Menu principal</p>
          <nav className="space-y-1">
            {modules.map(({ name, icon: Icon }) => <button key={name} onClick={() => setActive(name)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${active === name ? 'bg-[#f15a24] text-white shadow-[0_7px_20px_rgba(241,90,36,.15)]' : 'text-white/55 hover:bg-white/[.05] hover:text-white'}`}><Icon size={17} strokeWidth={1.8} /><span>{name}</span>{name === 'Registro' && <span className="ml-auto rounded-full bg-white/20 px-1.5 py-0.5 text-[10px]">3</span>}</button>)}
          </nav>
          <p className="mb-3 mt-8 px-3 text-[10px] font-semibold uppercase tracking-[.2em] text-white/30">Sistema</p>
          <nav className="space-y-1"><button className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-white/55 hover:bg-white/[.05] hover:text-white"><Settings size={17} />Configurações</button><button className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-white/55 hover:bg-white/[.05] hover:text-white"><ShieldCheck size={17} />Segurança</button></nav>
          <div className="mt-auto rounded-xl border border-white/[.07] bg-white/[.03] p-3"><div className="flex items-center gap-2"><span className="size-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" /><span className="text-xs font-medium">Bot online</span><span className="ml-auto text-[10px] text-white/35">v2.0.4</span></div></div>
        </div>
      </aside>

      <div className="lg:pl-[248px]">
        <header className="flex h-[76px] items-center justify-between border-b border-white/[.07] px-5 sm:px-8">
          <div><p className="text-xs text-white/35">IMPUNE / {active.toUpperCase()}</p><h1 className="mt-1 text-xl font-semibold tracking-tight">{active}</h1></div>
          <div className="flex items-center gap-3"><div className="relative hidden sm:block"><Search className="absolute left-3 top-2.5 text-white/30" size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Pesquisar..." className="h-9 w-48 rounded-lg border border-white/[.08] bg-white/[.03] pl-9 pr-3 text-xs outline-none placeholder:text-white/25 focus:border-[#f15a24]/60" /></div><button aria-label="Ajuda" className="rounded-lg p-2 text-white/45 hover:bg-white/[.05] hover:text-white"><CircleHelp size={19} /></button><div className="flex items-center gap-2 border-l border-white/[.08] pl-3"><div className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-orange-400 to-red-700 text-xs font-bold">P</div><div className="hidden text-right sm:block"><p className="text-xs font-medium">Pietro</p><p className="text-[10px] text-white/35">Administrador</p></div></div></div>
        </header>

        <div className="p-5 sm:p-8">
          <div className="relative mb-7 overflow-hidden rounded-2xl border border-[#f15a24]/20 bg-[#21120c] p-6 sm:p-8"><div className="absolute inset-0 bg-[url('/impune.png')] bg-cover bg-center opacity-[.12] mix-blend-screen" /><div className="relative"><p className="mb-2 text-[10px] font-semibold uppercase tracking-[.25em] text-[#ff8b5c]">IMPUNE SINCE 2022</p><h2 className="max-w-xl text-2xl font-bold tracking-tight sm:text-3xl">Tudo sob controle.<br /><span className="text-[#ff6b32]">Sua organização, mais forte.</span></h2><p className="mt-3 max-w-md text-sm leading-6 text-white/50">Gerencie sua operação, acompanhe sua equipe e mantenha cada sistema funcionando.</p></div><div className="absolute right-8 top-1/2 hidden -translate-y-1/2 text-[100px] font-black italic leading-none text-[#f15a24]/10 sm:block">I</div></div>

          <div className="mb-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[['Membros ativos','148','+12% este mês',Users],['Vendas no mês','R$ 86.420','+8,4% este mês',Store],['Pendências','3','Aguardando análise',ClipboardList],['Saldo do banco','R$ 24.890','Atualizado agora',Wallet]].map(([label, value, note, Icon]) => <div key={String(label)} className="rounded-xl border border-white/[.07] bg-[#12100f] p-5"><div className="mb-5 flex items-center justify-between"><span className="text-xs text-white/40">{label as string}</span><Icon size={17} className="text-[#f15a24]" /></div><p className="text-2xl font-semibold tracking-tight">{value as string}</p><p className="mt-1 text-[11px] text-emerald-400/80">{note as string}</p></div>)}</div>

          <div className="grid gap-5 xl:grid-cols-[1.3fr_1fr]">
            <section className="rounded-xl border border-white/[.07] bg-[#12100f] p-5"><div className="mb-5 flex items-center justify-between"><div><h3 className="font-medium">Atividade recente</h3><p className="mt-1 text-xs text-white/35">Últimas movimentações da organização</p></div><button className="text-xs text-[#ff7a43] hover:text-[#ff9a70]">Ver tudo <ChevronRight className="inline" size={13} /></button></div><div className="divide-y divide-white/[.06]">{activity.map(([title, desc, time], i) => <div key={title} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"><div className={`flex size-8 shrink-0 items-center justify-center rounded-lg ${i === 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-[#f15a24]/10 text-[#ff7a43]'}`}>{i === 0 ? <Users size={15} /> : <ArrowDownToLine size={15} />}</div><div className="min-w-0 flex-1"><p className="text-sm">{title}</p><p className="truncate text-xs text-white/35">{desc}</p></div><span className="text-[11px] text-white/30">{time}</span></div>)}</div></section>
            <section className="rounded-xl border border-white/[.07] bg-[#12100f] p-5"><div className="mb-5 flex items-center justify-between"><div><h3 className="font-medium">Acesso rápido</h3><p className="mt-1 text-xs text-white/35">Ações mais utilizadas</p></div><BarChart3 className="text-[#f15a24]" size={18} /></div><div className="grid grid-cols-2 gap-3">{['Abrir registro','Registrar venda','Enviar farm','Consultar banco'].map((label, i) => <button key={label} onClick={() => setShowModal(true)} className="group flex items-center gap-2 rounded-lg border border-white/[.07] bg-white/[.02] p-3 text-left text-xs transition hover:border-[#f15a24]/40 hover:bg-[#f15a24]/10"><Plus size={14} className="text-[#f15a24] transition group-hover:rotate-90" />{label}</button>)}</div></section>
          </div>
        </div>
      </div>
      {showModal && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-5 backdrop-blur-sm"><div className="w-full max-w-sm rounded-2xl border border-white/10 bg-[#171210] p-6 shadow-2xl"><div className="mb-5 flex items-center justify-between"><h2 className="font-semibold">Nova ação</h2><button onClick={() => setShowModal(false)} aria-label="Fechar" className="text-white/40 hover:text-white"><X size={18} /></button></div><p className="text-sm leading-6 text-white/55">Esta ação será enviada para o canal configurado no Discord. O bot Impune está pronto para receber a solicitação.</p><button onClick={() => setShowModal(false)} className="mt-6 w-full rounded-lg bg-[#f15a24] py-2.5 text-sm font-medium transition hover:bg-[#ff6b32]">Continuar</button></div></div>}
    </main>
  )
}
