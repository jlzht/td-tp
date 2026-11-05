/**
 * Cria o Google Forms da entrevista com o tomador de decisão (Teoria da Decisão, UFMG).
 *
 * Como usar: em script.google.com, crie um projeto, cole este arquivo, escolha a função
 * criarFormulario e clique em Executar (autorize o acesso ao Forms e ao Planilhas). Os links
 * do formulário, para enviar à pessoa entrevistada, e da planilha de respostas saem em
 * Execuções, no registro da execução.
 *
 * As perguntas repetem a entrevista de configuracoes/entrevista_decisor.json: as faixas são
 * as das 73 alternativas não dominadas, e as respostas viram os julgamentos par a par do AHP
 * e os limiares do ELECTRE I.
 */

const FORM_TITLE = 'Entrevista com o tomador de decisão: pilhas de minério';

const ASPECTS = [
  {key: 'custo', article: 'o', name: 'custo',
   gain: 'Custo: a compra de minério cai de R$ 65,5 milhões para R$ 59,6 milhões ' +
         '(economia de R$ 5,9 milhões, cerca de 10%).'},
  {key: 'silica', article: 'a', name: 'sílica',
   gain: 'Sílica: o desvio típico do teor de sílica de cada pilha em relação ao alvo do ' +
         'equipamento cai de 0,84 para 0,49 ponto percentual.'},
  {key: 'alumina', article: 'a', name: 'alumina',
   gain: 'Alumina: o desvio típico do teor de alumina de cada pilha em relação ao alvo do ' +
         'equipamento cai de 0,82 para 0,41 ponto percentual.'},
  {key: 'receita', article: 'a', name: 'receita parecida',
   gain: 'Receita parecida: a receita de cada pilha difere da receita comum do equipamento ' +
         'em 37% dos caminhões, em vez de 53%.'},
];

const INTENSITIES = [
  {label: 'extremamente mais', value: 9},
  {label: 'muito fortemente mais', value: 7},
  {label: 'fortemente mais', value: 5},
  {label: 'moderadamente mais', value: 3},
];

const INTRODUCTION =
  'Uma usina siderúrgica precisa decidir como compor 10 pilhas de minério que alimentam dois ' +
  'equipamentos de sinterização. Já existem 73 composições candidatas, todas eficientes: ' +
  'nenhuma é melhor que outra em todos os aspectos ao mesmo tempo. Escolher entre elas depende ' +
  'do que mais importa para a usina.\n\n' +
  'Pedimos que você responda como a pessoa responsável por essa escolha. Não há resposta ' +
  'certa e não é preciso conhecer métodos de decisão: as perguntas falam do problema, e o ' +
  'grupo calcula os pesos e os limiares do modelo a partir das suas respostas. Depois, o ' +
  'resultado pode voltar a você para confirmar se representa o que você pensa.\n\n' +
  'São quatro aspectos. Custo é o gasto com a compra dos minérios. Sílica e alumina medem o ' +
  'quanto o teor de cada pilha fica longe do alvo do equipamento. Receita parecida mede o ' +
  'quanto as pilhas de um mesmo equipamento seguem receitas (proporções de minérios) ' +
  'semelhantes, o que simplifica o trabalho no pátio. Para cada aspecto, damos o pior e o ' +
  'melhor valor existentes entre as 73 composições.\n\nTempo estimado: 5 minutos.';

class InterviewFormBuilder {
  /** Monta o formulário e a planilha de respostas. */
  build() {
    const form = FormApp.create(FORM_TITLE);
    form.setDescription(INTRODUCTION);
    form.setCollectEmail(false);
    form.setProgressBar(true);
    form.setShuffleQuestions(false);
    form.setConfirmationMessage('Obrigado! O grupo calculará os pesos e poderá voltar a você ' +
                                'para confirmar o resultado.');
    this.addImportance(form);
    this.addComparison(form);
    this.addComments(form);
    const sheet = SpreadsheetApp.create('Respostas: ' + FORM_TITLE);
    form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
    form.setPublished(true);
    form.setAcceptingResponses(true);
    return {form: form, sheet: sheet};
  }

  /** Parte 1: ordem de importância e intensidade de cada par de aspectos. */
  addImportance(form) {
    form.addPageBreakItem().setTitle('Parte 1: o que mais importa').setHelpText(
      'Em cada pergunta, considere a melhoria do PIOR para o MELHOR valor existente entre as ' +
      'composições, em um aspecto de cada vez:\n\n' +
      ASPECTS.map((aspect) => aspect.gain).join('\n'));
    const choices = ASPECTS.map((aspect) => aspect.gain);
    this.addChoice(form, 'Se você pudesse melhorar SÓ UM aspecto, do pior para o melhor valor, ' +
                   'qual traria MAIS valor para a usina?', choices);
    this.addChoice(form, 'Qual dos quatro traria MENOS valor, ou seja, qual você abriria mão ' +
                   'primeiro?', choices);
    form.addPageBreakItem().setTitle('Parte 1 (continuação): quanto mais importa').setHelpText(
      'Para cada par, diga quanto uma melhoria vale mais que a outra, sempre do pior para o ' +
      'melhor valor do aspecto. Os números entre parênteses só servem ao grupo para registrar a ' +
      'resposta.');
    const pairs = [[0, 1], [0, 2], [0, 3], [1, 2], [1, 3], [2, 3]];
    pairs.forEach(([first, second]) => this.addPair(form, ASPECTS[first], ASPECTS[second]));
  }

  /** Parte 2: tolerância à piora e apoio mínimo, que viram os limiares do ELECTRE I. */
  addComparison(form) {
    form.addPageBreakItem().setTitle('Parte 2: como comparar duas composições').setHelpText(
      'Ao comparar duas composições, uma pode ser melhor em alguns aspectos e pior em outros. ' +
      'As duas perguntas seguintes definem quando você aceita dizer que uma composição supera a ' +
      'outra.');
    this.addChoice(
      form,
      'Você aceita uma composição que seja pior em um aspecto desde que compense nos outros. ' +
      'Qual a maior piora que você toleraria em QUALQUER aspecto isolado? Meça como fração da ' +
      'faixa entre o melhor e o pior valor. Exemplo de 25% da faixa: R$ 1,5 milhão a mais de ' +
      'custo, ou sílica e alumina cerca de 0,09 ponto percentual mais longe do alvo.',
      ['Até 10% da faixa: quase não aceito piorar nenhum aspecto, mesmo que os outros melhorem muito',
       'Até 25% da faixa: aceito uma piora pequena em um aspecto se os outros compensarem',
       'Até 40% da faixa: aceito uma piora moderada em um aspecto, desde que não seja a maior parte da faixa',
       'Até 50% da faixa: aceito perder até metade da faixa em um aspecto se os demais ganharem']);
    this.addChoice(
      form,
      'Para considerar que a composição A é "pelo menos tão boa quanto" a B e descartar a B, os ' +
      'aspectos em que A é melhor ou igual a B precisam somar quanto da importância total? Por ' +
      'exemplo, se custo e sílica somam 70% da importância e A é melhor ou igual a B nesses dois, ' +
      'A tem 70% de apoio.',
      ['Pelo menos 60%: basta uma maioria folgada de importância a favor de A',
       'Pelo menos 70%: exijo uma boa maioria de importância a favor de A',
       'Pelo menos 80%: exijo que quase toda a importância esteja a favor de A',
       'Pelo menos 90%: só descarto B se A for melhor ou igual em praticamente tudo que importa']);
  }

  /** Observações livres, opcionais. */
  addComments(form) {
    form.addPageBreakItem().setTitle('Para terminar');
    form.addParagraphTextItem()
        .setTitle('Há algum aspecto importante para a usina que ficou de fora, ou alguma ' +
                  'observação sobre as suas respostas?')
        .setRequired(false);
  }

  /** Pergunta de múltipla escolha obrigatória, com as opções na ordem dada. */
  addChoice(form, title, labels) {
    return form.addMultipleChoiceItem().setTitle(title).setChoiceValues(labels).setRequired(true);
  }

  /** Quanto a melhoria de um aspecto vale mais, ou menos, que a de outro, em nove níveis. */
  addPair(form, first, second) {
    const title = 'Quanto vale mais melhorar ' + first.article + ' ' + first.name + ' ou melhorar ' +
                  second.article + ' ' + second.name + '?';
    const sentence = (winner, loser, intensity) =>
      'Melhorar ' + winner.article + ' ' + winner.name + ' vale ' + intensity.label +
      ' que melhorar ' + loser.article + ' ' + loser.name + ' (' + intensity.value + ')';
    const labels = INTENSITIES.map((intensity) => sentence(first, second, intensity))
        .concat(['As duas melhorias valem o mesmo (1)'])
        .concat(INTENSITIES.slice().reverse().map((intensity) => sentence(second, first, intensity)));
    return this.addChoice(form, title, labels);
  }
}

function criarFormulario() {
  const result = new InterviewFormBuilder().build();
  Logger.log('Link para enviar à pessoa entrevistada: ' + result.form.getPublishedUrl());
  Logger.log('Link para editar o formulário: ' + result.form.getEditUrl());
  Logger.log('Planilha de respostas: ' + result.sheet.getUrl());
}
