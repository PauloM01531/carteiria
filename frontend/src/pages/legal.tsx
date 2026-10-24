/** Rascunhos iniciais para REVISÃO antes de abrir a testadores externos (não é parecer jurídico). */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

function Doc({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <p className="rounded-xl border border-line bg-accent-soft px-4 py-2 text-sm">Versão preliminar, sujeita a revisão. Última atualização: 23/10/2026.</p>
      <h1 className="mt-6 font-display text-4xl font-semibold tracking-tight">{title}</h1>
      <div className="mt-6 flex flex-col gap-4 leading-relaxed [&_h2]:mt-4 [&_h2]:font-display [&_h2]:text-xl [&_h2]:font-semibold [&_li]:ml-5 [&_li]:list-disc">
        {children}
      </div>
    </article>
  )
}

export function PrivacyPage() {
  return (
    <Doc title="Aviso de privacidade">
      <p>Este aviso explica quais dados a CarteirIA coleta, por quê, como são guardados e como você pode exportá-los ou excluí-los, conforme a LGPD (Lei 13.709/2018).</p>
      <h2>Dados coletados</h2>
      <ul>
        <li>Conta: nome de exibição, e-mail e senha (guardada apenas como hash Argon2id, nunca em texto).</li>
        <li>Segurança: datas de cadastro e de acesso, endereço IP e navegador das sessões ativas, e registros de eventos de segurança.</li>
        <li>Finanças: os lançamentos, cartões, faturas, orçamentos e metas que você mesmo cadastrar.</li>
        <li>Preferências: tema e configurações da interface.</li>
      </ul>
      <h2>Finalidade</h2>
      <p>Os dados são usados exclusivamente para prestar o serviço de controle financeiro para você, proteger sua conta e cumprir obrigações legais. Seus dados financeiros não são vendidos, compartilhados para publicidade nem usados para treinar modelos de inteligência artificial ou para qualquer finalidade secundária.</p>
      <h2>Quem acessa</h2>
      <p>Somente você acessa seus dados financeiros. O isolamento é aplicado no servidor e no banco de dados. A administração da plataforma vê apenas dados de conta necessários para gerenciar acessos (nome, e-mail, situação e datas) e não tem acesso às suas finanças.</p>
      <h2>Armazenamento e segurança</h2>
      <p>Os dados ficam em banco PostgreSQL, com conexão protegida por HTTPS em produção, cópias de segurança protegidas e registros que não contêm senhas nem tokens.</p>
      <h2>Seus direitos</h2>
      <ul>
        <li>Acessar e corrigir seus dados de conta na página Perfil.</li>
        <li>Exportar seus dados (a exportação completa acompanha o módulo financeiro).</li>
        <li>Excluir sua conta a qualquer momento pela página Perfil. A exclusão remove definitivamente seus dados; mantemos apenas um registro técnico mínimo do evento (identificador interno e data), sem e-mail.</li>
      </ul>
      <h2>Contato</h2>
      <p>Dúvidas sobre privacidade podem ser enviadas ao administrador da plataforma pelo e-mail informado no convite ou na página inicial.</p>
      <Link to="/" className="font-semibold underline">Voltar ao início</Link>
    </Doc>
  )
}

export function TermsPage() {
  return (
    <Doc title="Termos de uso">
      <p>A CarteirIA é uma ferramenta de organização financeira pessoal oferecida em fase de testes.</p>
      <h2>Uso do serviço</h2>
      <ul>
        <li>O acesso é pessoal; não compartilhe sua senha.</li>
        <li>Você é responsável pelas informações que cadastra.</li>
        <li>A CarteirIA não é banco, corretora nem consultoria: os cálculos servem para organização e não constituem recomendação financeira.</li>
      </ul>
      <h2>Fase de testes</h2>
      <p>Por ser uma versão de testes, o serviço pode passar por mudanças, interrupções ou instabilidades. Não há garantia de disponibilidade contínua. Recomendamos exportar seus dados periodicamente.</p>
      <h2>Contas</h2>
      <p>O administrador pode aprovar, rejeitar ou suspender contas, por exemplo em caso de uso indevido. Você pode excluir sua conta quando quiser.</p>
      <h2>Alterações</h2>
      <p>Estes termos podem ser atualizados; mudanças relevantes serão comunicadas na plataforma.</p>
      <Link to="/" className="font-semibold underline">Voltar ao início</Link>
    </Doc>
  )
}

export function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <p className="font-display text-6xl font-semibold text-accent">404</p>
      <h1 className="mt-4 font-display text-2xl font-semibold">Página não encontrada</h1>
      <Link to="/" className="mt-6 font-semibold underline">Voltar ao início</Link>
    </div>
  )
}
