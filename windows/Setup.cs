using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Windows.Forms;
using Microsoft.Win32;
using System.ServiceProcess;

sealed class Setup : Form
{
    static readonly string[] Files = { "AcerFanControl.exe", "README.md", "LICENSE", "install-service.ps1", "uninstall.ps1" };
    static readonly string InstallDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), @"AcerFanControl");
    readonly Label heading = new Label();
    readonly Label description = new Label();
    readonly CheckBox startup = new CheckBox();
    readonly CheckBox desktop = new CheckBox();
    readonly CheckBox launch = new CheckBox();
    readonly Button next = new Button();
    readonly Button back = new Button();
    readonly Button cancel = new Button();
    readonly Label status = new Label();
    int page;
    bool installing;

    [STAThread]
    static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try
        {
            VerifyPayload();
            if (args.Length == 2 && args[0] == "--test-extract")
            {
                ExtractFiles(Path.GetFullPath(args[1]));
                foreach (string file in Files)
                {
                    using (var resource = Resource(file))
                    using (var actual = File.OpenRead(Path.Combine(args[1], file.Replace('/', Path.DirectorySeparatorChar))))
                    using (var sha = SHA256.Create())
                        if (Convert.ToBase64String(sha.ComputeHash(resource)) != Convert.ToBase64String(sha.ComputeHash(actual)))
                            throw new InvalidDataException("Payload mismatch: " + file);
                }
                return 0;
            }
            using (var wizard = new Setup())
            {
                if (args.Length == 2 && args[0] == "--preview")
                {
                    Directory.CreateDirectory(args[1]);
                    wizard.Show(); Application.DoEvents();
                    for (int p = 0; p < 3; p++)
                    {
                        wizard.page = p; wizard.Render(); Application.DoEvents();
                        using (var image = new Bitmap(wizard.Width, wizard.Height))
                        {
                            wizard.DrawToBitmap(image, new Rectangle(0, 0, image.Width, image.Height));
                            image.Save(Path.Combine(args[1], "page-" + p + ".png"), System.Drawing.Imaging.ImageFormat.Png);
                        }
                    }
                    wizard.Close(); return 0;
                }
                if (args.Length == 1 && args[0] == "--selftest")
                {
                    wizard.Advance();
                    if (wizard.page != 1 || !wizard.startup.Checked || !wizard.desktop.Checked) throw new Exception("Invalid options page.");
                    wizard.Back();
                    if (wizard.page != 0) throw new Exception("Back navigation failed.");
                    wizard.Advance();
                    wizard.startup.Checked = false;
                    wizard.desktop.Checked = false;
                    wizard.Back(); wizard.Advance();
                    if (wizard.startup.Checked || wizard.desktop.Checked) throw new Exception("Options not retained.");
                    return 0;
                }
                Application.Run(wizard);
            }
            return 0;
        }
        catch (Exception ex)
        {
            if (args.Length == 0) MessageBox.Show("Não foi possível abrir o instalador: " + ex.Message, "Acer Fan Control", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
    Setup()
    {
        Text = "Instalar Acer Fan Control";
        ClientSize = new Size(640, 430);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 10);
        BackColor = Color.White;
        Icon = SystemIcons.Application;
        heading.SetBounds(30, 28, 580, 40);
        heading.Font = new Font("Segoe UI", 18, FontStyle.Bold);
        description.SetBounds(32, 85, 574, 170);
        startup.SetBounds(32, 265, 570, 28);
        startup.Text = "Iniciar minimizado com o Windows"; startup.Checked = true;
        desktop.SetBounds(32, 300, 570, 28);
        desktop.Text = "Criar atalho na área de trabalho"; desktop.Checked = true;
        launch.SetBounds(32, 275, 570, 28);
        launch.Text = "Abrir o Acer Fan Control ao concluir"; launch.Checked = true;
        status.SetBounds(32, 332, 570, 26);
        back.SetBounds(305, 378, 94, 32); back.Text = "Voltar";
        next.SetBounds(407, 378, 104, 32);
        cancel.SetBounds(519, 378, 94, 32); cancel.Text = "Cancelar";
        back.Click += delegate { Back(); };
        next.Click += delegate { Advance(); };
        cancel.Click += delegate { Close(); };
        Controls.AddRange(new Control[] { heading, description, startup, desktop, launch, status, back, next, cancel });
        AcceptButton = next; CancelButton = cancel;
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (installing) e.Cancel = true; };
        Render();
    }
    void Back() { if (page == 1) { page = 0; Render(); } }
    void Advance()
    {
        if (page == 0) { page = 1; Render(); return; }
        if (page == 2)
        {
            if (launch.Checked)
            {
                try { Process.Start(new ProcessStartInfo(Path.Combine(InstallDirectory, "AcerFanControl.exe")) { WorkingDirectory = InstallDirectory }); }
                catch (Exception ex) { MessageBox.Show("A instalação está concluída, mas não foi possível abrir o aplicativo: " + ex.Message); return; }
            }
            Close(); return;
        }
        installing = true;
        next.Enabled = back.Enabled = cancel.Enabled = false;
        status.Text = "Instalando..."; UseWaitCursor = true; Application.DoEvents();
        try
        {
            Install(); page = 2; Render();
        }
        catch (Exception ex)
        {
            status.Text = "A instalação não foi concluída.";
            MessageBox.Show(ex.Message, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { installing = false; UseWaitCursor = false; next.Enabled = cancel.Enabled = true; back.Enabled = page == 1; }
    }
    void Render()
    {
        startup.Visible = desktop.Visible = page == 1;
        launch.Visible = page == 2;
        back.Enabled = page == 1;
        cancel.Visible = page != 2;
        status.Text = "";
        if (page == 0)
        {
            heading.Text = "Bem-vindo";
            description.Text = "Prévia de desenvolvimento para Windows 11 x64. Este assistente instala a interface e o serviço.\r\n\r\nHardware alvo: Acer Aspire A515-54G, placa Doc_WC e BIOS V1.24. Windows ainda não validado no hardware.\r\n\r\nO controle ainda depende do módulo AcerPmc3 assinado e da validação no notebook. Os botões ficam indisponíveis enquanto esses itens estiverem pendentes.";
            next.Text = "Avançar >";
        }
        else if (page == 1)
        {
            heading.Text = "Pronto para instalar";
            description.Text = "Pasta de instalação:\r\n" + InstallDirectory + "\r\n\r\nUm atalho também será criado no Menu Iniciar. Você poderá remover o aplicativo em Configurações > Aplicativos.\r\n\r\nEscolha as opções abaixo e clique em Instalar.";
            next.Text = "Instalar";
        }
        else
        {
            heading.Text = "Instalação concluída";
            description.Text = "A prévia do Acer Fan Control foi instalada.\r\n\r\nAbra o aplicativo pelo Menu Iniciar ou pelo atalho. Se iniciar minimizado, procure o ícone de ventoinha perto do relógio.\r\n\r\nControle pendente: obtenha o módulo AcerPmc3 assinado e valide no notebook antes de usar as ventoinhas.";
            next.Text = "Concluir";
        }
    }
    void Install()
    {
        if (!Environment.Is64BitOperatingSystem || !Environment.Is64BitProcess || String.Equals(Environment.GetEnvironmentVariable("PROCESSOR_ARCHITECTURE"), "ARM64", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Este instalador é para Windows x64.");
        string exe = Path.Combine(InstallDirectory, "AcerFanControl.exe");
        bool previousRunning = false;
        foreach (var process in Process.GetProcessesByName("AcerFanControl"))
            using (process) { try { if (String.Equals(process.MainModule.FileName, exe, StringComparison.OrdinalIgnoreCase)) previousRunning = true; } catch (Win32Exception) { } }
        foreach (var service in ServiceController.GetServices())
            using (service)
                if (service.ServiceName == "AcerFanControl" && service.Status != ServiceControllerStatus.Stopped)
                { service.Stop(); service.WaitForStatus(ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(15)); }
        if (previousRunning)
            foreach (var process in Process.GetProcessesByName("AcerFanControl"))
                using (process)
                    if (String.Equals(process.MainModule.FileName, exe, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidOperationException("Saia da interface pelo menu da bandeja antes de atualizar.");
        ExtractFiles(InstallDirectory);
        CreateShortcut(Environment.GetFolderPath(Environment.SpecialFolder.Programs), exe);
        if (desktop.Checked) CreateShortcut(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), exe);
        string powershell = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe");
        var installScript = new ProcessStartInfo(powershell, "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(InstallDirectory, "install-service.ps1") + "\" -Startup:" + (startup.Checked ? "$true" : "$false"));
        installScript.UseShellExecute = false; installScript.CreateNoWindow = true;
        using (var install = Process.Start(installScript))
        { if (!install.WaitForExit(30000) || install.ExitCode != 0) throw new InvalidOperationException("Não foi possível configurar o serviço. A instalação não foi concluída."); }
        using (var key = Registry.LocalMachine.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\AcerFanControl"))
        {
            key.SetValue("DisplayName", "Acer Fan Control (A515-54G) — Prévia Windows");
            key.SetValue("DisplayVersion", "0.1.0-preview");
            key.SetValue("Publisher", "Acer Fan Control");
            key.SetValue("InstallLocation", InstallDirectory);
            key.SetValue("DisplayIcon", exe + ",0");
            string uninstall = "\"" + Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), @"WindowsPowerShell\v1.0\powershell.exe") + "\" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + Path.Combine(InstallDirectory, "uninstall.ps1") + "\"";
            key.SetValue("UninstallString", uninstall); key.SetValue("QuietUninstallString", uninstall);
            key.SetValue("NoModify", 1, RegistryValueKind.DWord); key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            key.SetValue("EstimatedSize", 1024, RegistryValueKind.DWord);
        }
    }
    static void CreateShortcut(string folder, string exe)
    {
        Type type = Type.GetTypeFromProgID("WScript.Shell");
        dynamic shell = Activator.CreateInstance(type);
        dynamic shortcut = shell.CreateShortcut(Path.Combine(folder, "Acer Fan Control.lnk"));
        try
        {
            shortcut.TargetPath = exe; shortcut.WorkingDirectory = InstallDirectory;
            shortcut.IconLocation = exe + ",0"; shortcut.Description = "Acer Fan Control · Aspire A515-54G";
            shortcut.Save();
        }
        finally { System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shortcut); System.Runtime.InteropServices.Marshal.FinalReleaseComObject(shell); }
    }
    static Stream Resource(string file)
    {
        Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload." + file.Replace('/', '.'));
        if (stream == null) throw new InvalidDataException("Arquivo ausente no instalador: " + file);
        return stream;
    }
    static void VerifyPayload()
    {
        using (var resource = Resource("AcerFanControl.exe")) VerifyHash(resource, "APP_HASH");

        foreach (string file in Files) using (var resource = Resource(file)) if (resource.Length == 0) throw new InvalidDataException("Arquivo vazio: " + file);
    }
    static void VerifyHash(Stream stream, string expected)
    {
        using (var sha = SHA256.Create())
            if (BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "") != expected) throw new InvalidDataException("O instalador está danificado.");
    }
    static void ExtractFiles(string folder)
    {
        Directory.CreateDirectory(folder);
        foreach (string file in Files)
        {
            string path = Path.Combine(folder, file.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            using (var input = Resource(file)) using (var output = File.Create(path)) input.CopyTo(output);
        }
    }
}


