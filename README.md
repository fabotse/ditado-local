# Ditado local

Segure o **Alt da direita**, fale e solte: o texto aparece onde o cursor estiver, em qualquer programa
(WhatsApp, Chrome, Word, Bloco de Notas...). Roda **100% no seu computador**, sem conta, sem assinatura e sem mandar a
sua voz para a internet. Para Windows 10 e 11.

A transcrição é feita pelo Whisper (`large-v3-turbo`, via [faster-whisper](https://github.com/SYSTRAN/faster-whisper)).
Numa placa NVIDIA, 10 segundos de fala viram texto em menos de meio segundo.

## Instalar

1. Instale o [Python 3.12](https://www.python.org/downloads/release/python-3126/). Na instalação, marque **Add python.exe to PATH**.
2. Baixe este repositório (botão verde **Code → Download ZIP**) e descompacte numa pasta.
3. Dê dois cliques em **`instalar.bat`**. Ele cria um Python só para o app, dentro da pasta, e não mexe no resto do PC.
4. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele baixa o modelo de voz (~1,6 GB) para a pasta `modelo/`.
   Depois disso, funciona sem internet.

Para desinstalar, apague a pasta.

## Usar

- **Segure o Alt da direita** e fale. Aparece uma pílula vermelha embaixo da tela enquanto grava.
- **Solte**: a pílula fica âmbar enquanto transcreve, e o texto é colado no campo onde está o cursor.
- O que você tinha copiado antes **continua copiado**: o app guarda a sua área de transferência e devolve depois de colar,
  e o texto ditado não entra no histórico do Win+V.
- Se não houver campo de texto, o texto fica copiado e aparece o aviso "Copiado. Cole com Ctrl+V".
- Alt da direita **com outra tecla** (AltGr+2 = @, AltGr+E = €) continua funcionando normalmente.
- Para sair, feche a janela preta do `iniciar.bat`.

## Ajustes (opcionais)

Variáveis de ambiente, antes de abrir o `iniciar.bat`:

| Variável | Padrão | Para quê |
|---|---|---|
| `DITADO_IDIOMA` | `pt` | Outro idioma: `en`, `es`... |
| `DITADO_MODELO` | `large-v3-turbo` | Num PC sem placa NVIDIA, `small` é bem mais rápido (e erra mais). |
| `DITADO_DISPOSITIVO` | automático | `cpu` ou `cuda`, para forçar. |

## Limites conhecidos

- Sem placa NVIDIA, a transcrição roda no processador: funciona, mas leva alguns segundos por frase.
- Programas abertos **como administrador** não recebem o texto. É uma proteção do Windows; para ditar neles, abra o
  `iniciar.bat` como administrador também.
- No Bloco de Notas do Windows 11, de vez em quando (2 em 12 nos nossos testes) a colagem não entra. Repita o ditado.
- Não há formatação inteligente nem dicionário pessoal: o texto sai como o Whisper entende.

## Como foi feito

Este app nasceu de um vídeo: estudamos **como** um app de ditado comercial funciona por dentro, com o
[REA](https://github.com/morluto/rea) (engenharia reversa com IA), e construímos o nosso do zero. Nenhum código, texto
ou imagem do app comercial foi usado. Este projeto não tem relação com o Wispr Flow nem com os seus criadores.

Vídeo: *(link quando publicar)*

## Licença

MIT. Pode usar, mudar e distribuir.
