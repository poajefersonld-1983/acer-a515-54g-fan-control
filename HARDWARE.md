# Validação de hardware e limites

Este documento registra resultados de um único equipamento. Não amplia a lista de compatibilidade.

- DMI: Aspire A515-54G; placa Doc_WC; BIOS V1.24.
- Intel Core i5-10210U e NVIDIA GeForce MX250.
- ITE IT8987, revisão 3; PMC3 ativo, dados em 0x6a e comando/status em 0x6e.
- Fedora 44, kernel 7.2.8-200.fc44.x86_64.

PMC3 0x7e lê PWM6; 0x7d seguido de um byte solicita PWM6. Antes de controlar, o programa verifica chip, configuração das portas, PWM6 em 0x1808, seleção de CTR1 e CTR1=255. Não altera divisor, frequência, polaridade, ativação de dispositivo lógico nem flash. Os seletores usados para a leitura I2EC são restaurados. Leia `pmc3.py` para todas as verificações.

O intervalo manual é 183–255. O aplicativo repete a solicitação a cada aproximadamente 150 ms porque o firmware continua com sua rotina automática habilitada. Leituras EC: temperatura CPU em 0x0558; tacômetro CPU em 0x055c/0x055d, big endian. Os RPM foram comparados com a interface de firmware durante os testes.

| PWM solicitado | Percentual aproximado | Mediana de RPM estabilizado |
|---|---:|---:|
| 183 | 72% | 4.744 |
| 208 | 82% | 5.097 |
| 232 | 91% | 5.404 |
| 255 | 100% | 5.780 |

Em máximo, a faixa observada foi aproximadamente 5.750–5.972 RPM. Não se tentou exceder PWM 255 nem modificar frequência para ultrapassar o limite do controlador. O ajuste controla a ventoinha física do notebook, não uma ventoinha independente da MX250.

Persistência validada: perfil máximo mantido sem interface aberta (~5.734 RPM em uma amostra); manual PWM 217 recuperado após reiniciar o serviço (~5.146 RPM); automático recuperado após reiniciar o serviço; botão Salvar da interface seguido de fechamento da janela manteve o máximo (~5.780 RPM em uma amostra).

Os testes cobrem fechamento da janela e reinício do serviço, que carrega o mesmo perfil na inicialização. O serviço foi habilitado no systemd; um reboot completo não é registrado como teste aqui. Suspensão/retomada e outras versões de BIOS não foram validadas.

Referências de pesquisa: [acer_a515_acpi](https://github.com/embeddedt/acer_a515_acpi) e [documentação ITE discutida em lm-sensors](https://github.com/lm-sensors/lm-sensors/issues/320). A configuração desse outro projeto não correspondeu ao firmware deste equipamento; aplicar seus valores diretamente não foi necessário para este controlador.
