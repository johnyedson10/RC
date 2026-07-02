# 30-junho-lidar-com-experia-do-usuario-cadastro

## Objetivo
[x] Melhorar a experiência do usuário nas telas de cadastro e login.
[x] Corrigir o comportamento das mensagens de feedback para que elas não fiquem fixas na tela.
[x] Garantir que os valores digitados pelo usuário permaneçam visíveis quando ocorrer erro de validação.

## Contexto do problema
[x] Hoje as mensagens de `flash` aparecem e permanecem fixas na interface.
[x] Isso gera poluição visual e dá a impressão de que a tela travou.
[x] Quando acontece uma validação inválida, o usuário perde parte do que digitou.
[x] O fluxo precisa ficar mais amigável, claro e previsível.

## O que precisa ser feito

### 1. Melhorar as mensagens de feedback
[x] Transformar as mensagens de retorno em notificações visuais temporárias.
[x] Exibir cada mensagem por aproximadamente `20 segundos`.
[x] Depois desse tempo, a mensagem deve desaparecer automaticamente.
[x] Evitar que o feedback fique preso no layout após o envio do formulário.
[x] Manter suporte às mensagens atuais do Flask `flash`, mas com comportamento visual melhor.

### 2. Preservar o estado dos campos
[x] Quando o usuário errar o cadastro ou login, os campos já preenchidos devem continuar preenchidos.
[x] O usuário não deve precisar digitar tudo de novo após uma falha de validação.
[x] Aplicar isso principalmente nos campos de:
  [x] nome
  [x] e-mail
  [x] senha, quando fizer sentido para a experiência
[x] Se houver campos sensíveis, pensar com cuidado antes de persistir o valor.

### 3. Usar uma biblioteca JavaScript para apoiar a experiência
[x] Adotar uma biblioteca JavaScript leve para exibir mensagens temporárias.
[x] Preferência sugerida: `Notyf` ou outra biblioteca equivalente de toast/notification.
[x] A biblioteca deve permitir:
  [x] duração configurável
  [x] visual limpo
  [x] fácil integração com o HTML atual
[x] Se necessário, complementar com JavaScript próprio para restaurar valores dos inputs.

## Requisitos de implementação

### Mensagens
[x] O feedback deve ser visível sem ocupar permanentemente espaço na tela.
[x] A mensagem precisa sumir automaticamente depois de 20 segundos.
[x] Se houver várias mensagens, elas devem aparecer de forma organizada.
[x] O usuário deve entender claramente se a ação deu certo ou deu errado.

### Estado dos inputs
[x] Os dados digitados devem ser mantidos após redirecionamento ou retorno de validação.
[x] O estado dos campos precisa ser restaurado de forma consistente.
[x] O comportamento deve funcionar no cadastro e no login.
[x] Não quebrar a navegação atual do projeto.

## Sugestão de abordagem
[x] Revisar o template principal onde os formulários de autenticação ficam.
[x] Substituir a exibição fixa das mensagens por toasts ou alertas temporários.
[x] Configurar a duração para `20000 ms`.
[x] Armazenar temporariamente os valores digitados com `sessionStorage` ou outro mecanismo simples.
[x] Restaurar os valores quando a página recarregar após um erro.
[x] Limpar os dados salvos quando o envio for bem-sucedido.

## Critérios de aceite
[x] A mensagem de feedback não fica mais fixa na tela.
[x] O feedback some automaticamente após 20 segundos.
[x] Os campos digitados continuam preenchidos após falha de validação.
[x] O cadastro e o login continuam funcionando normalmente.
[x] A solução permanece simples, legível e fácil de manter.

## Resultado esperado
[x] Uma experiência de usuário mais fluida.
[x] Menos frustração ao corrigir erros de cadastro.
[x] Feedback visual claro sem poluir a interface.
[x] Reuso do fluxo atual do projeto com melhorias pontuais.
