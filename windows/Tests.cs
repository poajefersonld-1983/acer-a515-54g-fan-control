using System;
using System.IO;
using AcerFanControl;
sealed class Fake : IDevice
{
    public int temperature = 45, written, restores;
    public bool fail, disposed;
    public Sample Read() { if (fail) throw new IOException("simulated sensor failure"); return new Sample { cpu_c = temperature, rpm = 4800, pwm = written }; }
    public void Set(int pwm) { written = pwm; }
    public void Restore() { restores++; }
    public void Dispose() { Restore(); disposed = true; }
}
static class Tests
{
    static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
    static void Reject(Action action) { bool rejected=false; try { action(); } catch { rejected=true; } Assert(rejected, "Invalid input accepted"); }
    static int Main(string[] args)
    {
        try
        {
            string folder = args[0]; Directory.CreateDirectory(folder);
            string path = Path.Combine(folder, Guid.NewGuid().ToString("N") + ".json");
            Hardware.Check("Aspire A515-54G", "Doc_WC", "V1.24");
            Reject(delegate { Hardware.Check("Aspire A515-54G", "Doc_WC", "V1.25"); });
            Reject(delegate { Hardware.Check("ASUS", "Doc_WC", "V1.24"); });
            Reject(delegate { Controller.Validate(new Profile { mode="manual", pwm=182 }); });
            Reject(delegate { Controller.Validate(new Profile { mode="manual", pwm=256 }); });
            Reject(delegate { Controller.Validate(new Profile { mode="raw", pwm=200 }); });
            var fake = new Fake();
            using (var control = new Controller(fake, path))
            {
                control.Tick(DateTime.UtcNow); Assert(fake.written == 0, "Automatic mode writes manual PWM");
                control.Command("manual", 208); control.Tick(DateTime.UtcNow); Assert(fake.written == 208, "Manual PWM");
                fake.temperature=85; control.Tick(DateTime.UtcNow); Assert(fake.written==255 && control.Current.thermal_override, "Thermal override");
                fake.temperature=45; control.Tick(DateTime.UtcNow); Assert(fake.written==208, "Recovery from thermal override");
                control.Command("save",183); Assert(File.Exists(path), "Profile not saved");
                var persisted = new Fake(); using (var reloaded = new Controller(persisted,path)) { reloaded.Tick(DateTime.UtcNow); Assert(persisted.written==208, "Saved manual profile not restored"); }
                control.Command("max",183); control.Tick(DateTime.UtcNow.AddSeconds(16)); Assert(fake.written==208, "Temporary command did not revert to saved profile");
                control.Command("auto",183); Assert(fake.restores>0, "Automatic mode did not restore");
                fake.fail=true; Reject(delegate { control.Tick(DateTime.UtcNow); }); Assert(control.Current.mode=="auto", "Failure did not return to automatic");
            }
            Assert(fake.disposed, "Device not disposed");
            var restart = new Fake(); using (var control = new Controller(restart,path)) { control.Tick(DateTime.UtcNow); Assert(restart.written==0, "Saved automatic mode not restored"); }
            Console.WriteLine("PASS: hardware guards, PWM limits, thermal override, persistence, timeout and restoration."); return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine(ex); return 1; }
    }
}

