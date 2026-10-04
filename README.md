# Acer A515-54G Fan Control

Controle de ventoinha para Linux, com interface GTK 4 em português, RPM, temperatura da CPU e temperatura da GPU NVIDIA quando disponível. Inclui os modos **Automático**, **Personalizado (72–100%)**, **Máximo** e **Salvar e manter funcionando**. Um serviço systemd mantém o perfil salvo após fechar a janela e o recupera na próxima inicialização.

**Compatibilidade validada:** Acer Aspire **A515-54G**, placa **Doc_WC**, BIOS **V1.24**, controlador ITE **IT8987**, Fedora 44. O código recusa outras identificações ou configurações do controlador. A presença de uma MX250, sozinha, não garante compatibilidade: o controle depende da placa e do firmware do notebook.

No equipamento testado, o máximo estabilizou em aproximadamente **5.800 RPM**, com pico observado de **5.972 RPM**. RPM varia com alimentação e condições físicas; 100% representa PWM 255/255, não uma promessa de RPM fixa. Consulte [HARDWARE.md](HARDWARE.md) para medições e limites.

## Instalação no Fedora

Abra um terminal na sua sessão gráfica e execute como usuário normal:

```bash
git clone https://github.com/poajefersonld-1983/acer-a515-54g-fan-control.git
cd acer-a515-54g-fan-control
bash install-deps-fedora.sh
bash install-panel.sh
"$HOME/.local/bin/acer-fan-control"
```

Também é possível baixar **Code → Download ZIP**, extrair e executar os scripts na pasta extraída. Não execute a interface nem o instalador de atalhos com sudo. O instalador copia o aplicativo para `~/.local/share/acer-fan-control`, cria o comando em `~/.local/bin` e adiciona atalhos ao menu e à pasta Desktop configurada pelo sistema. Depois da instalação, a pasta baixada pode ser movida sem quebrar os atalhos.

Na interface, clique em **Conectar**. Na primeira conexão, autorize a instalação do serviço com sua senha na janela do Polkit. O teste de identificação e dos limites do controlador precisa passar antes da instalação. A sessão gráfica deve ter um agente de autenticação Polkit (normalmente já presente no KDE/GNOME).

As dependências são instaladas pelos repositórios do sistema: veja [DEPENDENCIES.md](DEPENDENCIES.md). Não é necessário compilar módulo de kernel, usar pip, configurar Coolbits nem instalar os projetos citados como referências.

## Uso e persistência

1. **Automático:** o firmware regula a ventoinha; selecionar esse modo também limpa o perfil manual salvo.
2. **Personalizado:** ajuste o controle entre 72% e 100%. A interface converte o percentual em PWM inteiro; o mínimo autorizado é 183/255.
3. **Máximo:** solicita PWM 255/255 continuamente.
4. **Salvar e manter funcionando:** grava o modo atual. Ele continua com a janela fechada e volta na próxima inicialização.

Uma alteração manual sem salvar é temporária: ao fechar/desconectar a interface, o serviço volta ao último perfil salvo. Se não houver perfil manual salvo, volta ao automático. A opção **Automático** tem efeito imediato e persistente; não é necessário salvar depois dela.

Em modo manual ou máximo, se a leitura de CPU atingir 85 °C, o serviço usa PWM 255 enquanto a temperatura permanecer elevada. Essa proteção não substitui as proteções térmicas do notebook. A rotina automática do firmware permanece habilitada durante o controle.

O serviço fica associado ao usuário que o instalou. A interface comum não recebe acesso genérico de escrita ao EC; o serviço aceita apenas os comandos definidos e os valores limitados. Não execute simultaneamente outro programa que controle o mesmo EC/ventoinha.

## Verificação e diagnóstico

```bash
/usr/bin/python3 check-deps.py
/usr/bin/python3 -m unittest discover -s . -p 'test_*.py' -v
systemctl status acer-fan-control.service
journalctl -u acer-fan-control.service -b --no-pager
```

Os testes unitários verificam comandos e persistência usando arquivos temporários; não acessam hardware. A confirmação de operação real é feita observando o RPM na interface: compare Automático e Máximo, salve um perfil, feche a janela e reabra para conferir o perfil recuperado. As medições já realizadas no equipamento de referência estão em [HARDWARE.md](HARDWARE.md).

Se aparecer **Hardware/BIOS não validado**, pare: não remova os testes de identidade e não copie offsets de outro notebook. Outras versões de BIOS precisam de validação própria. Se `/dev/port` for bloqueado pelo kernel ou pela política de segurança, o serviço falhará; isso não é resolvido instalando bibliotecas Python. Temperatura NVIDIA ausente não impede o controle da ventoinha; ela depende do comando opcional `nvidia-smi` do driver NVIDIA.

O perfil fica em `/var/lib/acer-fan-control/profile.json`; a conexão local fica em `/run/acer-fan-control/control.sock`. Evite editar o perfil manualmente. Para voltar ao controle do firmware, selecione Automático. Para interromper o serviço, use `sudo systemctl stop acer-fan-control.service`; a parada normal restaura o PWM anterior e deixa a rotina do firmware ativa.

## Atualização

Feche a interface, atualize a pasta baixada e reinstale os arquivos de usuário:

```bash
git pull --ff-only
bash install-panel.sh
pkexec /usr/bin/python3 -I "$HOME/.local/share/acer-fan-control/setup-service.py"
```

O último comando atualiza também os arquivos do serviço e o reinicia. A atualização preserva o perfil salvo. Atualizações apenas da interface não exigem reinstalar o serviço.

## Remoção

Primeiro selecione **Automático** na interface e feche-a. Na pasta do projeto, execute:

```bash
bash uninstall.sh
```

O script remove os arquivos do aplicativo e o serviço, preservando o perfil e a identificação do usuário em `/var/lib/acer-fan-control`. Para remover também esses dois arquivos conhecidos após desinstalar:

```bash
sudo rm -f /var/lib/acer-fan-control/profile.json /var/lib/acer-fan-control/uid
sudo rmdir /var/lib/acer-fan-control
```

## Código e licença

`panel.py`: interface; `pmc3.py`: protocolo e validação; `backend.py`: validação dos comandos; `daemon.py`: serviço e persistência; `setup-service.py`: instalação privilegiada. Os scripts de instalação, diagnóstico de dependências, remoção, ícone e testes acompanham o código.

Licença MIT, consulte [LICENSE](LICENSE). Referências de pesquisa: [embeddedt/acer_a515_acpi](https://github.com/embeddedt/acer_a515_acpi), [foucault/nvfancontrol](https://github.com/foucault/nvfancontrol) e a discussão sobre documentação ITE em [lm-sensors #320](https://github.com/lm-sensors/lm-sensors/issues/320). Esses projetos não são dependências de execução. O perfil ACPI de outro A515 não foi aplicado ao equipamento de referência.
