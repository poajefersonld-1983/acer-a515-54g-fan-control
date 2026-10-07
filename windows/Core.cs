using System;
using System.IO;
using System.Management;
using System.Runtime.InteropServices;
using System.Threading;
using System.Web.Script.Serialization;

namespace AcerFanControl
{
    public sealed class Sample { public int cpu_c, rpm, pwm; public bool thermal_override; public string mode, error; }
    public interface IDevice : IDisposable { Sample Read(); void Set(int pwm); void Restore(); }
    public sealed class Profile { public string mode = "auto"; public int pwm = 183; }
    public static class Hardware
    {
        public static void Check(string product, string board, string bios)
        {
            if (product != "Aspire A515-54G" || board != "Doc_WC" || bios != "V1.24")
                throw new InvalidOperationException("Hardware/BIOS não validado. Requer Aspire A515-54G, placa Doc_WC e BIOS V1.24.");
        }
        public static void Validate()
        {
            Check(Read("Win32_ComputerSystem", "Model"), Read("Win32_BaseBoard", "Product"), Read("Win32_BIOS", "SMBIOSBIOSVersion"));
        }
        static string Read(string table, string property)
        {
            using (var query = new ManagementObjectSearcher("SELECT " + property + " FROM " + table))
            using (var rows = query.Get())
                foreach (ManagementObject row in rows) using (row) return Convert.ToString(row[property]).Trim();
            throw new InvalidOperationException("Não foi possível identificar o hardware.");
        }
    }
    public sealed class PawnDevice : IDevice
    {
        IntPtr library, handle;
        Open open; Load load; Execute execute;
        Mutex bus;
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Open(out IntPtr handle);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Load(IntPtr handle, byte[] blob, UIntPtr size);
        [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Ansi)] delegate int Execute(IntPtr handle, [MarshalAs(UnmanagedType.LPStr)] string name, ulong[] input, UIntPtr inputCount, [Out] ulong[] output, UIntPtr outputCount, out UIntPtr count);
        public PawnDevice()
        {
            Hardware.Validate(); // Must run before opening any hardware transport.
            string module = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "AcerPmc3.bin");
            if (!File.Exists(module)) throw new InvalidOperationException("Prévia Windows: módulo AcerPmc3 assinado ainda pendente. Controle indisponível.");
            string folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "PawnIO");
            string dll = Path.Combine(folder, "PawnIOLib.dll");
            if (!File.Exists(dll)) throw new InvalidOperationException("Instale a edição oficial assinada do PawnIO em pawnio.eu.");
            try
            {
                library = LoadLibraryEx(dll, IntPtr.Zero, 0x8);
                if (library == IntPtr.Zero) throw new InvalidOperationException("Não foi possível carregar PawnIOLib.");
                open = Resolve<Open>("pawnio_open"); load = Resolve<Load>("pawnio_load"); execute = Resolve<Execute>("pawnio_execute");
                Check(open(out handle));
                byte[] blob = File.ReadAllBytes(module); Check(load(handle, blob, (UIntPtr)blob.Length));
                bus = new Mutex(false, @"Global\Access_ISABUS.HTP.Method");
                Call("ioctl_validate", new ulong[0], 0);
            }
            catch { Dispose(); throw; }
        }
        T Resolve<T>(string name) { IntPtr proc = GetProcAddress(library, name); if (proc == IntPtr.Zero) throw new InvalidOperationException("PawnIO incompatível."); return (T)(object)Marshal.GetDelegateForFunctionPointer(proc, typeof(T)); }
        static void Check(int hr) { if (hr < 0) Marshal.ThrowExceptionForHR(hr); }
        ulong[] Call(string name, ulong[] input, int count)
        {
            bool held = false;
            try
            {
                try { held = bus.WaitOne(1000); } catch (AbandonedMutexException) { held = true; }
                if (!held) throw new InvalidOperationException("Controlador ocupado por outro monitor.");
                var output = new ulong[count]; UIntPtr written;
                Check(execute(handle, name, input, (UIntPtr)input.Length, output, (UIntPtr)count, out written));
                if (written.ToUInt64() != (ulong)count) throw new InvalidOperationException("Resposta incompleta do controlador.");
                return output;
            }
            finally { if (held) bus.ReleaseMutex(); }
        }
        public Sample Read() { var data = Call("ioctl_sample", new ulong[0], 3); return new Sample { cpu_c = (int)data[0], rpm = (int)data[1], pwm = (int)data[2] }; }
        public void Set(int pwm) { if (pwm < 183 || pwm > 255) throw new ArgumentOutOfRangeException("pwm"); Call("ioctl_set_pwm", new ulong[] { (ulong)pwm }, 0); }
        public void Restore() { if (handle != IntPtr.Zero && bus != null) Call("ioctl_restore", new ulong[0], 0); }
        public void Dispose()
        {
            try { Restore(); }
            finally
            {
                if (handle != IntPtr.Zero) { CloseHandle(handle); handle = IntPtr.Zero; }
                if (bus != null) { bus.Dispose(); bus = null; }
                if (library != IntPtr.Zero) { FreeLibrary(library); library = IntPtr.Zero; }
            }
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryEx(string path, IntPtr file, uint flags);
        [DllImport("kernel32.dll", CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module, string name);
        [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    }
    public sealed class Controller : IDisposable
    {
        readonly IDevice device;
        readonly string profileFile;
        Profile saved = new Profile();
        Profile active = new Profile();
        public Sample Current = new Sample { mode = "auto" };
        DateTime lastHeartbeat = DateTime.UtcNow;
        bool temporary;
        public Controller(IDevice device, string profileFile)
        {
            this.device = device; this.profileFile = profileFile;
            try { if (File.Exists(profileFile)) { saved = new JavaScriptSerializer().Deserialize<Profile>(File.ReadAllText(profileFile)); Validate(saved); } }
            catch { device.Dispose(); throw; }
            active = Copy(saved);
        }
        public static void Validate(Profile profile)
        {
            if (profile == null || (profile.mode != "auto" && profile.mode != "manual" && profile.mode != "max") || profile.pwm < 183 || profile.pwm > 255)
                throw new InvalidOperationException("Perfil inválido. Manual: PWM 183–255 (72–100%).");
        }
        static Profile Copy(Profile p) { return new Profile { mode = p.mode, pwm = p.pwm }; }
        public void Command(string action, int pwm)
        {
            lastHeartbeat = DateTime.UtcNow;
            if (action == "status") return;
            if (action == "save")
            {
                WriteProfile(active); saved = Copy(active); temporary = false; return;
            }
            if (action == "disconnect") { active = Copy(saved); temporary = false; if (active.mode == "auto") device.Restore(); return; }
            var next = new Profile { mode = action, pwm = action == "max" ? 255 : pwm };
            Validate(next);
            if (action == "auto") { device.Restore(); WriteProfile(next); saved = Copy(next); temporary = false; }
            else temporary = true;
            active = next;
        }
        void WriteProfile(Profile p)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(profileFile));
            string staged = profileFile + ".tmp";
            File.WriteAllText(staged, new JavaScriptSerializer().Serialize(p));
            if (File.Exists(profileFile)) File.Replace(staged, profileFile, null); else File.Move(staged, profileFile);
        }
        public void Tick(DateTime now)
        {
            try
            {
                if (temporary && now - lastHeartbeat > TimeSpan.FromSeconds(15)) { active = Copy(saved); temporary = false; if (active.mode == "auto") device.Restore(); }
                Sample sample = device.Read();
                if (sample.cpu_c < 0 || sample.cpu_c > 125 || sample.rpm < 0 || sample.rpm > 20000) throw new InvalidOperationException("Sensores fora dos limites esperados.");
                sample.mode = active.mode; sample.thermal_override = active.mode != "auto" && sample.cpu_c >= 85;
                if (active.mode != "auto") device.Set(sample.thermal_override || active.mode == "max" ? 255 : active.pwm);
                Current = sample;
            }
            catch (Exception ex)
            {
                try { device.Restore(); } catch { }
                active = new Profile(); temporary = false;
                Current = new Sample { mode = "auto", error = ex.Message };
                throw;
            }
        }
        public void Dispose() { device.Dispose(); }
    }
}

