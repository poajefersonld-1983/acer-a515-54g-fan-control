using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.ServiceProcess;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace AcerFanControl
{
    sealed class FanService : ServiceBase
    {
        readonly object gate = new object();
        Controller controller;
        Thread worker, server;
        volatile bool stopping;
        string fault = "Prévia Windows: módulo assinado e validação no Acer pendentes.";
        readonly string profile = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), @"AcerFanControl\profile.json");
        public FanService() { ServiceName = "AcerFanControl"; CanShutdown = true; CanHandlePowerEvent = true; }
        protected override void OnStart(string[] args)
        {
            stopping = false;
            worker = new Thread(Work); worker.IsBackground = true; worker.Start();
            server = new Thread(Serve); server.IsBackground = true; server.Start();
        }
        void Work()
        {
            while (!stopping)
            {
                lock (gate)
                {
                    try
                    {
                        if (controller == null) { controller = new Controller(new PawnDevice(), profile); fault = null; }
                        controller.Tick(DateTime.UtcNow);
                    }
                    catch (Exception ex)
                    {
                        fault = ex.Message;
                        if (controller != null) { try { controller.Dispose(); } catch { } controller = null; }
                    }
                }
                Thread.Sleep(controller == null ? 5000 : 150);
            }
        }
        void Serve()
        {
            var acl = new PipeSecurity();
            acl.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.NetworkSid, null), PipeAccessRights.ReadWrite, AccessControlType.Deny));
            acl.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null), PipeAccessRights.FullControl, AccessControlType.Allow));
            acl.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null), PipeAccessRights.ReadWrite, AccessControlType.Allow));
            while (!stopping)
            {
                try
                {
                    using (var pipe = new NamedPipeServerStream("AcerFanControl", PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 4096, 4096, acl))
                    {
                        var connection = pipe.BeginWaitForConnection(null, null);
                        while (!stopping && !connection.AsyncWaitHandle.WaitOne(200)) { }
                        if (stopping) break;
                        pipe.EndWaitForConnection(connection);
                        using (var reader = new StreamReader(pipe))
                        using (var writer = new StreamWriter(pipe) { AutoFlush = true })
                        {
                            // Pipe ACL denies network logons and accepts only local administrators.
                            var lineTask = reader.ReadLineAsync();
                            if (!lineTask.Wait(2000)) continue;
                            string line = lineTask.Result;
                            if (line == null || line.Length > 128) continue;
                            string[] parts = line.Split(' '); int pwm = 183;
                            if (parts.Length > 2 || (parts.Length == 2 && !Int32.TryParse(parts[1], out pwm))) continue;
                            Sample response;
                            lock (gate)
                            {
                                if (controller == null) response = new Sample { mode = "auto", error = fault };
                                else
                                {
                                    try { controller.Command(parts[0], pwm); controller.Tick(DateTime.UtcNow); response = controller.Current; }
                                    catch (Exception ex) { response = new Sample { mode = "auto", error = ex.Message }; }
                                }
                            }
                            writer.WriteLine(new JavaScriptSerializer().Serialize(response));
                        }
                    }
                }
                catch { if (!stopping) Thread.Sleep(200); }
            }
        }
        protected override bool OnPowerEvent(PowerBroadcastStatus status)
        {
            if (status == PowerBroadcastStatus.Suspend) lock (gate) { if (controller != null) { try { controller.Dispose(); } catch { } controller = null; } }
            return true;
        }
        protected override void OnStop()
        {
            stopping = true;
            if (worker != null) worker.Join(6000);
            if (server != null) server.Join(3000);
            lock (gate) { if (controller != null) { controller.Dispose(); controller = null; } }
        }
        protected override void OnShutdown() { OnStop(); }
        public void TestService()
        {
            OnStart(new string[0]);
            try
            {
                using (var pipe = new NamedPipeClientStream(".", "AcerFanControl", PipeDirection.InOut))
                {
                    pipe.Connect(5000);
                    using (var reader = new StreamReader(pipe))
                    using (var writer = new StreamWriter(pipe) { AutoFlush = true })
                    {
                        writer.WriteLine("status"); var reply = reader.ReadLineAsync();
                        if (!reply.Wait(3000)) throw new Exception("IPC timeout.");
                        var sample = new JavaScriptSerializer().Deserialize<Sample>(reply.Result);
                        if (sample.error == null) throw new Exception("Service test must refuse unsupported hardware or missing signed module.");
                    }
                }
            }
            finally { OnStop(); }
        }
    }
    sealed class Panel : Form
    {
        readonly Label sensors = new Label(), status = new Label();
        readonly NumericUpDown percent = new NumericUpDown();
        readonly Button automatic = new Button(), manual = new Button(), maximum = new Button(), save = new Button();
        readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
        readonly NotifyIcon tray = new NotifyIcon();
        bool exiting, pending;
        public Panel()
        {
            Text = "Acer Fan Control · A515-54G · Prévia Windows";
            ClientSize = new Size(630, 360); StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 10); FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
            BackColor = Color.FromArgb(24, 29, 37); ForeColor = Color.White;
            var title = new Label { Text = "Acer Fan Control", Font = new Font("Segoe UI", 22, FontStyle.Bold), AutoSize = true, Location = new Point(24, 20) };
            var subtitle = new Label { Text = "Aspire A515-54G • Doc_WC • BIOS V1.24", AutoSize = true, Location = new Point(26, 67) };
            sensors.SetBounds(26, 111, 580, 40); sensors.Font = new Font("Segoe UI", 15); sensors.Text = "CPU: — °C     Ventoinha: — RPM";
            percent.SetBounds(26, 181, 80, 30); percent.Minimum = 72; percent.Maximum = 100; percent.Value = 85;
            var percentage = new Label { Text = "%", Location = new Point(112, 185), AutoSize = true };
            Button[] buttons = { automatic, manual, maximum, save };
            string[] labels = { "Automático", "Aplicar ajuste", "Máximo", "Salvar perfil" };
            for (int i = 0; i < buttons.Length; i++) { buttons[i].SetBounds(26 + i * 145, 232, 135, 38); buttons[i].Text = labels[i]; buttons[i].FlatStyle = FlatStyle.Flat; }
            status.SetBounds(26, 287, 577, 57); status.Text = "Prévia: aguardando serviço. Controle depende do módulo assinado e da validação no Acer.";
            Controls.AddRange(new Control[] { title, subtitle, sensors, percent, percentage, automatic, manual, maximum, save, status });
            automatic.Click += delegate { Query("auto"); };
            manual.Click += delegate { Query("manual " + Math.Max(183, (int)Math.Round((double)percent.Value * 255 / 100))); };
            maximum.Click += delegate { Query("max"); };
            save.Click += delegate { Query("save"); };
            tray.Icon = SystemIcons.Application; tray.Text = "Acer Fan Control — prévia"; tray.Visible = true;
            var menu = new ContextMenuStrip();
            menu.Items.Add("Abrir", null, delegate { Show(); Activate(); });
            menu.Items.Add("Automático", null, delegate { Query("auto"); });
            menu.Items.Add("Sair da interface", null, delegate { exiting = true; Query("disconnect"); Close(); });
            tray.ContextMenuStrip = menu; tray.DoubleClick += delegate { Show(); Activate(); };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (!exiting && e.CloseReason == CloseReason.UserClosing) { e.Cancel = true; Query("disconnect"); Hide(); } };
            FormClosed += delegate { timer.Dispose(); tray.Visible = false; tray.Dispose(); menu.Dispose(); };
            timer.Interval = 1000; timer.Tick += delegate { Query("status"); }; timer.Start();
        }
        void Query(string action)
        {
            if (pending) return; pending = true;
            var worker = new System.ComponentModel.BackgroundWorker();
            worker.DoWork += delegate(object sender, System.ComponentModel.DoWorkEventArgs e)
            {
                using (var pipe = new NamedPipeClientStream(".", "AcerFanControl", PipeDirection.InOut, PipeOptions.Asynchronous, TokenImpersonationLevel.Impersonation))
                {
                    pipe.Connect(1500);
                    using (var reader = new StreamReader(pipe))
                    using (var writer = new StreamWriter(pipe) { AutoFlush = true })
                    {
                        writer.WriteLine(action); var read = reader.ReadLineAsync();
                        if (!read.Wait(2500)) throw new IOException("Tempo limite de resposta do serviço.");
                        e.Result = new JavaScriptSerializer().Deserialize<Sample>(read.Result);
                    }
                }
            };
            worker.RunWorkerCompleted += delegate(object sender, System.ComponentModel.RunWorkerCompletedEventArgs e)
            {
                pending = false; worker.Dispose(); if (IsDisposed) return;
                var sample = e.Error == null ? e.Result as Sample : null;
                bool ready = sample != null && sample.error == null;
                automatic.Enabled = manual.Enabled = maximum.Enabled = save.Enabled = ready;
                sensors.Text = ready ? "CPU: " + sample.cpu_c + " °C     Ventoinha: " + sample.rpm + " RPM" : "CPU: — °C     Ventoinha: — RPM";
                status.Text = ready ? (sample.thermal_override ? "Proteção térmica: máximo enquanto CPU ≥ 85 °C." : "Modo: " + sample.mode + ". Salvar perfil mantém o ajuste com a janela fechada.") : sample != null ? sample.error : "Serviço indisponível. Execute o instalador e abra como administrador.";
            };
            worker.RunWorkerAsync();
        }
        public void Screenshot(string path)
        {
            timer.Stop(); Show(); Application.DoEvents();
            automatic.Enabled = manual.Enabled = maximum.Enabled = save.Enabled = false;
            status.Text = "Prévia Windows: controle indisponível até receber o módulo AcerPmc3 assinado e validar no notebook.";
            using (var image = new Bitmap(Width, Height)) { DrawToBitmap(image, new Rectangle(0,0,Width,Height)); image.Save(path); }
            exiting = true; Close();
        }
    }
    static class Program
    {
        [STAThread] static int Main(string[] args)
        {
            if (args.Length > 0 && args[0] == "--service") { ServiceBase.Run(new FanService()); return 0; }
            if (args.Length > 0 && args[0] == "--service-selftest") { try { using (var service = new FanService()) service.TestService(); return 0; } catch { return 1; } }
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && args[0] == "--preview") { using (var panel = new Panel()) panel.Screenshot(args[1]); return 0; }
            bool created;
            using (var mutex = new Mutex(true, @"Local\AcerFanControlWindows", out created))
            {
                if (!created) return 0;
                using (var panel = new Panel()) { if (args.Length > 0 && args[0] == "--minimized") panel.Shown += delegate { panel.Hide(); }; Application.Run(panel); }
            }
            return 0;
        }
    }
}

