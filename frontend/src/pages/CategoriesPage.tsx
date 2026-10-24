import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Alert, Button, Card, Field, Segmented, Spinner, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { Category, Kind } from '../lib/finance'

export default function CategoriesPage() {
  const [items, setItems] = useState<Category[] | null>(null)
  const [kind, setKind] = useState<Kind>('expense')
  const [name, setName] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null)

  const load = useCallback(() => api<Category[]>('/categories?include_inactive=true').then(setItems).catch((e) => setError(e.message)), [])
  useEffect(() => {
    load()
  }, [load])

  async function create(e: FormEvent) {
    e.preventDefault()
    const v = name.trim() ? (name.trim().length > 60 ? 'Use no máximo 60 caracteres.' : null) : 'Informe o nome.'
    setFieldError(v)
    if (v) return
    setSaving(true)
    setError(null)
    try {
      await api('/categories', { method: 'POST', body: { name: name.trim(), kind } })
      setName('')
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Erro.')
    } finally {
      setSaving(false)
    }
  }

  async function update(id: string, body: Record<string, unknown>) {
    setError(null)
    try {
      await api(`/categories/${id}`, { method: 'PATCH', body })
      setEditing(null)
      load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Erro.')
    }
  }

  const list = (items ?? []).filter((c) => c.kind === kind)
  const custom = list.filter((c) => !c.is_system)
  const system = list.filter((c) => c.is_system)

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Categorias</h1>
        <p className="mt-1 text-sm text-muted">Crie categorias próprias. Desativar uma categoria preserva os lançamentos antigos.</p>
      </header>
      <Segmented label="Tipo" value={kind} onChange={setKind} options={[{ value: 'expense', label: 'Despesas' }, { value: 'income', label: 'Receitas' }]} />
      {error && <Alert kind="error">{error}</Alert>}
      <Card>
        <form onSubmit={create} noValidate className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field label={`Nova categoria de ${kind === 'expense' ? 'despesa' : 'receita'}`} className="flex-1" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} error={fieldError} />
          <Button type="submit" loading={saving}>Adicionar</Button>
        </form>
      </Card>
      {items === null ? (
        <Spinner />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <h2 className="font-display text-xl font-semibold">Suas categorias</h2>
            {custom.length === 0 ? (
              <p className="mt-3 text-sm text-muted">Você ainda não criou categorias deste tipo.</p>
            ) : (
              <ul className="mt-3 divide-y divide-line">
                {custom.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                    {editing?.id === c.id ? (
                      <form className="flex flex-1 gap-2" onSubmit={(e) => { e.preventDefault(); update(c.id, { name: editing.name }) }}>
                        <input aria-label="Nome da categoria" value={editing.name} maxLength={60} onChange={(e) => setEditing({ id: c.id, name: e.target.value })} className="min-h-9 flex-1 rounded-lg border border-line bg-surface px-2" autoFocus />
                        <Button type="submit" className="min-h-9 px-3">Salvar</Button>
                        <Button type="button" variant="ghost" className="min-h-9 px-3" onClick={() => setEditing(null)}>Cancelar</Button>
                      </form>
                    ) : (
                      <>
                        <span className={cx('font-semibold', !c.active && 'text-muted line-through')}>{c.name}</span>
                        <span className="flex gap-1">
                          <Button variant="ghost" className="min-h-9 px-3" onClick={() => setEditing({ id: c.id, name: c.name })}>Renomear</Button>
                          <Button variant="ghost" className="min-h-9 px-3" onClick={() => update(c.id, { active: !c.active })}>{c.active ? 'Desativar' : 'Reativar'}</Button>
                        </span>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <h2 className="font-display text-xl font-semibold">Categorias padrão</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {system.map((c) => (
                <span key={c.id} className="rounded-full bg-surface-2 px-3 py-1 text-sm">{c.name}</span>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}
