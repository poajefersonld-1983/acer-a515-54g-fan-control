# Módulo PMC3 pendente de assinatura

`AcerPmc3.p` é código-fonte para a interface oficial PawnIO. Não é um driver de kernel separado e não está pronto para instalação. O compilador gera `AcerPmc3.amx`; a edição oficial assinada do PawnIO exige um blob assinado aceito pelo seu verificador.

Compilação validada com Pawn 4.1.7152 e os cabeçalhos de `namazso/PawnIO.Modules`:

```powershell
pawncc AcerPmc3.p -iCAMINHO_DOS_CABECALHOS -C64 '-;+' '-(+' -p
```

Operações públicas: validar controlador/configuração, ler CPU/RPM/PWM, solicitar PWM 183–255 e restaurar. Não há ioctl de portas ou endereços arbitrários. A identificação SMBIOS é verificada pelo aplicativo antes de abrir o transporte. O módulo também verifica IT8987, configuração PMC3 e limites PWM6.

O duty atual é capturado antes da primeira alteração manual e restaurado em `ioctl_restore` ou `unload`; a rotina automática do firmware permanece habilitada. Chamadas de usuários devem manter o mutex ISA global, e a restauração em unload precisa de revisão de concorrência com os drivers ACPI do Windows no hardware alvo.

Não foi solicitada nem obtida assinatura. O binário sem assinatura não deve ser renomeado para `.bin` ou apresentado como utilizável com PawnIO oficial. Não use edição irrestrita nem desative proteções do Windows como etapa de instalação desta prévia.

Próximas etapas: revisão/assinatura pelo projeto PawnIO e validação no Aspire A515-54G / Doc_WC / BIOS V1.24 com Windows 11. Testar restauração em parada, encerramento inesperado e suspensão/retomada antes de declarar suporte.

