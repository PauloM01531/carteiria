import { Link } from 'react-router-dom'

const features = [
  {
    title: 'Parcelas do jeito certo',
    text: 'Uma compra de R$ 1.200,00 em 12 vezes pesa R$ 100,00 em cada fatura, não R$ 1.200,00 todo mês.',
  },
  {
    title: 'Seus dados são só seus',
    text: 'Cada conta é isolada no banco de dados. Nem a administração navega pelas suas finanças.',
  },
  {
    title: 'Orçamentos e metas',
    text: 'Defina limites por categoria, acompanhe o quanto já usou e veja o que ainda está comprometido.',
  },
  {
    title: 'No computador e no celular',
    text: 'Interface pensada para telas pequenas, com tema claro e escuro.',
  },
]

function InstallmentIllustration() {
  const months = ['nov', 'dez', 'jan', 'fev', 'mar', 'abr']
  return (
    <div className="relative mx-auto w-full max-w-md" aria-hidden>
      <div className="absolute -inset-4 -z-10 rotate-2 rounded-[2rem] bg-accent-soft" />
      <div className="rounded-[1.75rem] border border-line bg-surface p-6 shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-muted">Exemplo</p>
            <p className="mt-1 font-display text-2xl font-semibold">Notebook novo</p>
          </div>
          <span className="rounded-full bg-brand px-3 py-1 text-xs font-bold text-brand-contrast">12x</span>
        </div>
        <p className="tabular mt-4 text-sm text-muted">
          Total <span className="font-semibold text-ink">R$ 1.200,00</span>
        </p>
        <div className="mt-5 grid grid-cols-6 items-end gap-2">
          {months.map((m, i) => (
            <div key={m} className="flex flex-col items-center gap-1.5">
              <div className="w-full rounded-lg bg-accent" style={{ height: 36, opacity: 1 - i * 0.1 }} />
              <span className="text-[11px] font-semibold uppercase text-muted">{m}</span>
            </div>
          ))}
        </div>
        <div className="tabular mt-5 flex items-center justify-between rounded-xl bg-surface-2 px-4 py-3 text-sm">
          <span className="text-muted">Em cada fatura</span>
          <span className="font-display text-xl font-semibold">R$ 100,00</span>
        </div>
      </div>
    </div>
  )
}

export default function Landing() {
  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6">
      <section className="grid items-center gap-12 py-10 sm:py-16 lg:grid-cols-[1.1fr_1fr]">
        <div>
          <p className="inline-flex rounded-full border border-line bg-surface px-3 py-1 text-xs font-semibold text-muted">
            Versão de testes · acesso por aprovação
          </p>
          <h1 className="mt-5 font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            Seu dinheiro, <span className="italic text-accent">sem surpresa</span> na fatura.
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted">
            A CarteirIA organiza receitas, despesas, cartões e parcelas para você saber quanto pode gastar hoje e quanto já está
            comprometido amanhã.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Link to="/cadastro" className="inline-flex min-h-12 items-center justify-center rounded-xl bg-brand px-6 font-semibold text-brand-contrast">
              Solicitar acesso
            </Link>
            <Link to="/entrar" className="inline-flex min-h-12 items-center justify-center rounded-xl border border-line bg-surface px-6 font-semibold">
              Já tenho conta
            </Link>
          </div>
        </div>
        <InstallmentIllustration />
      </section>

      <section className="grid gap-4 pb-16 sm:grid-cols-2 lg:grid-cols-4">
        {features.map((f) => (
          <article key={f.title} className="rounded-2xl border border-line bg-surface p-5">
            <h2 className="font-display text-lg font-semibold">{f.title}</h2>
            <p className="mt-2 text-sm text-muted">{f.text}</p>
          </article>
        ))}
      </section>
    </div>
  )
}
