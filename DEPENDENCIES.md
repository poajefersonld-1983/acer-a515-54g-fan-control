# Dependências

Ambiente validado: Fedora 44, Python 3.14, GTK 4, sessão KDE e systemd. O controlador requer Linux x86 com acesso privilegiado a `/dev/port` e a identificação exata descrita no README. A interface usa Python do sistema (`/usr/bin/python3`).

| Componente | Pacote Fedora | Função |
|---|---|---|
| Python 3 | `python3` | Interface e serviço; biblioteca padrão para JSON, socket e arquivos |
| PyGObject | `python3-gobject` | Bindings e introspecção GTK |
| Pycairo | `python3-cairo` | Gráfico de RPM |
| GTK 4 | `gtk4` | Interface gráfica |
| Polkit / pkexec | `polkit` | Autorização para instalar o serviço |
| systemd | `systemd` | Serviço em segundo plano e inicialização |
| Pastas XDG | `xdg-user-dirs` | Localizar Desktop |
| Ferramentas desktop | `desktop-file-utils` | Validar e registrar atalhos |
| GLib / GIO | `glib2` | Integração desktop |
| Git | `git` | Baixar e atualizar o projeto (opcional com ZIP) |

Instalação: `bash install-deps-fedora.sh`. Verificação sem acesso ao hardware: `/usr/bin/python3 check-deps.py`. As versões exatas não são travadas: utilize os pacotes da sua distribuição. O Fedora resolve suas dependências transitivas.

Não há dependências pip. Instalar `gi` via pip ou executar um Python de ambiente virtual não substitui os bindings do sistema. Não há dependência de GCC, headers de kernel, NBFC, nvfancontrol nem acer_a515_acpi.

`nvidia-smi` é opcional e vem do driver NVIDIA instalado separadamente; serve apenas à leitura da temperatura da GPU. Um agente Polkit na sessão gráfica é necessário para o diálogo de autorização. KDE e GNOME normalmente fornecem esse agente; sessões mínimas precisam configurá-lo.

Outras distribuições não foram validadas neste equipamento. Adapte os nomes de pacotes usando a documentação da distribuição e confirme GTK 4, PyGObject, cairo, pkexec, systemd e as ferramentas XDG. O instalador automático de dependências recusa sistemas que não sejam Fedora.

Fontes dos pacotes: [Python GObject no Fedora](https://packages.fedoraproject.org/pkgs/pygobject3/python3-gobject/), [Polkit no Fedora](https://packages.fedoraproject.org/pkgs/polkit/polkit/).
