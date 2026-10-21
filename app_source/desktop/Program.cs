using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace TakeStudio;

static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        using var mutex = new Mutex(true, @"Local\TakeStudio.Desktop.1", out bool first);
        using var activate = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\TakeStudio.Activate.1");
        if (!first) { activate.Set(); return; }
        using var form = new StudioWindow(args.Contains("--smoke"));
        var registration = ThreadPool.RegisterWaitForSingleObject(activate, (_, _) => {
            if (form.IsHandleCreated && !form.IsDisposed) form.BeginInvoke(() => { form.WindowState = FormWindowState.Normal; form.Show(); form.Activate(); });
        }, null, Timeout.Infinite, false);
        Application.Run(form);
        registration.Unregister(null);
    }
}

sealed class StudioWindow : Form
{
    readonly string packageRoot = AppContext.BaseDirectory;
    readonly string dataRoot;
    readonly string token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    readonly HttpClient client = new() { Timeout = TimeSpan.FromSeconds(8) };
    readonly Panel splash = new() { Dock=DockStyle.Fill, BackColor=Color.FromArgb(16,19,18) };
    readonly Label title = new() { Text="목소리를 만들 준비를 합니다", ForeColor=Color.FromArgb(237,242,235), AutoSize=false, TextAlign=ContentAlignment.MiddleCenter, Font=new Font("Malgun Gothic",22,FontStyle.Bold) };
    readonly Label detail = new() { Text="실행 환경을 확인하고 있습니다.", ForeColor=Color.FromArgb(174,190,174),AutoSize=false,TextAlign=ContentAlignment.MiddleCenter,Font=new Font("Malgun Gothic",11) };
    readonly Label phase = new() { Text="TAKE STUDIO  /  LOCAL VOICE WORKSPACE",ForeColor=Color.FromArgb(196,245,108),AutoSize=false,TextAlign=ContentAlignment.MiddleCenter,Font=new Font("Segoe UI",9) };
    readonly Button retry = new() { Text="다시 시작", Visible=false,FlatStyle=FlatStyle.Flat,BackColor=Color.FromArgb(196,245,108),ForeColor=Color.FromArgb(21,32,25) };
    readonly Button logs = new() { Text="로그 폴더",Visible=false,FlatStyle=FlatStyle.Flat,ForeColor=Color.FromArgb(210,224,198) };
    readonly PictureBox mark = new() { SizeMode=PictureBoxSizeMode.Zoom };
    readonly CancellationTokenSource lifetime = new();
    readonly bool smoke;
    Process? server;
    WebView2? web;
    IntPtr processJob;
    string origin="";
    bool closing, booting;
    readonly object logGuard = new();

    public StudioWindow(bool smokeTest)
    {
        smoke=smokeTest;
        dataRoot=Environment.GetEnvironmentVariable("TAKE_DATA_DIR") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"TakeStudio");
        Directory.CreateDirectory(Path.Combine(dataRoot,"logs"));
        Text="Take Studio"; Width=1380; Height=930; MinimumSize=new Size(950,700); StartPosition=FormStartPosition.CenterScreen;
        BackColor=Color.FromArgb(16,19,18); Font=new Font("Segoe UI",10);
        Icon=Icon.ExtractAssociatedIcon(Environment.ProcessPath!);
        mark.Image=Image.FromStream(Assembly.GetExecutingAssembly().GetManifestResourceStream("TakeStudio.Icon.png")!);
        splash.Controls.AddRange([mark,phase,title,detail,retry,logs]); Controls.Add(splash);
        splash.Resize += (_,_)=>LayoutSplash(); LayoutSplash();
        retry.Click+=async (_,_)=>await Boot();
        logs.Click+=(_,_)=>Process.Start(new ProcessStartInfo(Path.Combine(dataRoot,"logs")){UseShellExecute=true});
        Shown+=async (_,_)=>await Boot();
        FormClosing+=OnClosing;
    }
    void LayoutSplash()
    {
        int mid=splash.ClientSize.Height/2;
        mark.SetBounds(splash.ClientSize.Width/2-40,mid-155,80,80);
        phase.SetBounds(20,mid-49,splash.ClientSize.Width-40,24);
        title.SetBounds(20,mid-13,splash.ClientSize.Width-40,54);
        detail.SetBounds(50,mid+52,splash.ClientSize.Width-100,70);
        retry.SetBounds(splash.ClientSize.Width/2-135,mid+140,130,42);
        logs.SetBounds(splash.ClientSize.Width/2+5,mid+140,130,42);
    }
    void Log(string message)
    {
        lock(logGuard) File.AppendAllText(Path.Combine(dataRoot,"logs","desktop.log"),DateTimeOffset.Now.ToString("O")+" "+message+Environment.NewLine,Encoding.UTF8);
    }
    int FindPort()
    {
        for(int p=38765;p<38785;p++) {try {var listener=new TcpListener(IPAddress.Loopback,p);listener.Start();listener.Stop();return p;}catch(SocketException){}}
        throw new IOException("사용 가능한 로컬 연결을 찾지 못했습니다. 다른 Take Studio 창을 닫아 주세요.");
    }
    async Task Boot()
    {
        if(booting || closing)return; booting=true; retry.Visible=logs.Visible=false; splash.Visible=true; splash.BringToFront();
        try
        {
            StopServer();
            var app=Path.Combine(packageRoot,"app"); var python=Path.Combine(packageRoot,"runtime","python","python.exe");
            if(!File.Exists(python)||!File.Exists(Path.Combine(app,"app.py")))throw new IOException("앱 파일이 부족합니다. 압축을 모두 풀고 app·runtime·Take Studio.exe를 같은 폴더에 두세요.");
            title.Text="로컬 작업실을 열고 있습니다";detail.Text="인터넷 연결 없이 서버를 시작합니다.";
            int port=FindPort(); origin=$"http://127.0.0.1:{port}";
            var start=new ProcessStartInfo(python){WorkingDirectory=app,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
            start.ArgumentList.Add("-u");start.ArgumentList.Add("app.py");
            start.Environment.Remove("PYTHONHOME");start.Environment.Remove("PYTHONPATH");
            start.Environment["NUMBA_CACHE_DIR"]=Path.Combine(dataRoot,"cache","numba");
            foreach(var pair in new Dictionary<string,string>{{"TAKE_PORT",port.ToString()},{"TAKE_DATA_DIR",dataRoot},{"TAKE_SESSION_TOKEN",token},{"TAKE_PRELOAD","1"},{"TAKE_RESIDENT","1"},{"PYTHONUTF8","1"},{"HF_HUB_OFFLINE","1"},{"TRANSFORMERS_OFFLINE","1"},{"DO_NOT_TRACK","1"}})start.Environment[pair.Key]=pair.Value;
            server=new Process{StartInfo=start,EnableRaisingEvents=true};
            server.OutputDataReceived+=(_,e)=>{if(e.Data!=null)Log(e.Data);};server.ErrorDataReceived+=(_,e)=>{if(e.Data!=null)Log(e.Data);};
            server.Exited+=(_,_)=>{
                if(closing||booting||IsDisposed||!IsHandleCreated)return;
                BeginInvoke(()=>{if(closing)return;splash.Visible=true;splash.BringToFront();title.Text="로컬 작업실 연결이 끊겼습니다";detail.Text="다시 시작하면 저장된 테이크를 불러옵니다.";retry.Visible=logs.Visible=true;});
            };
            server.Start(); processJob=Native.AttachKillOnClose(server.Handle); server.BeginOutputReadLine();server.BeginErrorReadLine();
            client.DefaultRequestHeaders.Remove("X-Take-Token");client.DefaultRequestHeaders.Add("X-Take-Token",token);
            Log("Server launched, port="+port+", pid="+server.Id);
            JsonDocument? status=null;
            for(int attempt=0;attempt<80;attempt++)
            {
                lifetime.Token.ThrowIfCancellationRequested();
                if(server.HasExited)throw new IOException("서버를 시작하지 못했습니다. 로그 폴더에서 자세한 내용을 확인할 수 있습니다.");
                try{status=JsonDocument.Parse(await client.GetStringAsync(origin+"/api/status",lifetime.Token));break;}catch(HttpRequestException){}catch(TaskCanceledException) when(!lifetime.IsCancellationRequested){}
                await Task.Delay(500,lifetime.Token);
            }
            if(status==null)throw new IOException("로컬 서버 연결 시간이 초과됐습니다. 다시 시작해 주세요.");
            using(status){if(status.RootElement.GetProperty("app").GetString()!="take-studio")throw new IOException("연결된 서버를 확인하지 못했습니다.");}
            await PrepareWebView();
            title.Text="음성 모델을 준비하고 있습니다";
            bool modelReady=false;string? loadedModel=null;
            for(int attempt=0;attempt<300;attempt++)
            {
                lifetime.Token.ThrowIfCancellationRequested();
                using var s=JsonDocument.Parse(await client.GetStringAsync(origin+"/api/status",lifetime.Token));
                var engine=s.RootElement.GetProperty("engine"); var stage=engine.GetProperty("status").GetString();
                detail.Text=engine.GetProperty("message").GetString()+"\n첫 준비에는 잠시 시간이 걸릴 수 있습니다.";
                if(stage=="ready"){modelReady=true;loadedModel=s.RootElement.GetProperty("selected_tts_engine").GetString();break;}
                if(stage=="error"||stage=="stopped")throw new IOException(engine.GetProperty("message").GetString());
                await Task.Delay(2000,lifetime.Token);
            }
            if(!modelReady)throw new IOException("모델 준비 시간이 초과됐습니다. GPU 메모리를 확보한 뒤 다시 시작해 주세요.");
            splash.Visible=false; web!.Visible=true; web.BringToFront();
            Log("Desktop ready; model resident.");
            if(smoke){File.WriteAllText(Path.Combine(dataRoot,"desktop-smoke.json"),JsonSerializer.Serialize(new{ready=true,serverPid=server.Id,origin,modelPreloaded=true,selectedModel=loadedModel,version="1.0.0-rc1"})); await Task.Delay(3000);closing=true;Close();}
        }
        catch(OperationCanceledException) when(closing){}
        catch(Exception) when(closing){}
        catch(Exception exc){Log(exc.ToString());title.Text="시작을 완료하지 못했습니다";detail.Text=exc.Message;retry.Visible=logs.Visible=true;StopServer();if(smoke){File.WriteAllText(Path.Combine(dataRoot,"desktop-smoke.json"),JsonSerializer.Serialize(new{ready=false,error=exc.ToString()}));closing=true;Close();}}
        finally{booting=false;}
    }
    async Task PrepareWebView()
    {
        if(web!=null){web.Dispose();web=null;}
        try{CoreWebView2Environment.GetAvailableBrowserVersionString();}
        catch(WebView2RuntimeNotFoundException){throw new IOException("화면 표시 구성 요소가 없습니다. prerequisites 폴더의 Microsoft WebView2 오프라인 설치 파일을 실행한 뒤 다시 열어 주세요.");}
        web=new WebView2{Dock=DockStyle.Fill,Visible=false,DefaultBackgroundColor=Color.FromArgb(16,19,18)};Controls.Add(web);
        var environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(dataRoot,"webview"));
        await web.EnsureCoreWebView2Async(environment);
        web.CoreWebView2.Settings.AreDevToolsEnabled=false; web.CoreWebView2.Settings.IsStatusBarEnabled=false;
        web.CoreWebView2.Settings.AreDefaultContextMenusEnabled=false;
        var cookie=web.CoreWebView2.CookieManager.CreateCookie("take_session",token,"127.0.0.1","/");cookie.IsHttpOnly=true;cookie.SameSite=CoreWebView2CookieSameSiteKind.Strict;
        web.CoreWebView2.CookieManager.AddOrUpdateCookie(cookie);
        web.CoreWebView2.NavigationStarting+=(_,e)=>{if(!e.Uri.StartsWith(origin+"/",StringComparison.Ordinal))e.Cancel=true;};
        web.CoreWebView2.NewWindowRequested+=(_,e)=>e.Handled=true;
        web.CoreWebView2.PermissionRequested+=(_,e)=>{
            if(e.Uri.StartsWith(origin+"/",StringComparison.Ordinal)&&e.PermissionKind==CoreWebView2PermissionKind.Microphone&&e.IsUserInitiated)
                e.State=MessageBox.Show(this,"직접 녹음하려면 마이크 접근이 필요합니다. 녹음은 이 PC에서 처리됩니다.","마이크 사용",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes?CoreWebView2PermissionState.Allow:CoreWebView2PermissionState.Deny;
            else e.State=CoreWebView2PermissionState.Deny;
        };
        web.CoreWebView2.DownloadStarting+=(_,e)=>{
            using var save=new SaveFileDialog{FileName=Path.GetFileName(e.ResultFilePath),InitialDirectory=Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),Filter="모든 파일|*.*"};
            if(save.ShowDialog(this)==DialogResult.OK)e.ResultFilePath=save.FileName;else e.Cancel=true;
            e.Handled=true;
        };
        web.CoreWebView2.ProcessFailed+=(_,_)=>{splash.Visible=true;splash.BringToFront();title.Text="화면 연결이 끊겼습니다";detail.Text="다시 시작하면 저장된 테이크를 불러옵니다.";retry.Visible=logs.Visible=true;};
        var loaded=new TaskCompletionSource<bool>();
        web.CoreWebView2.NavigationCompleted+=(_,e)=>loaded.TrySetResult(e.IsSuccess);
        web.Source=new Uri(origin+"/");
        if(!await loaded.Task.WaitAsync(TimeSpan.FromSeconds(30),lifetime.Token))
            throw new IOException("앱 화면을 불러오지 못했습니다. 다시 시작해 주세요.");
    }
    async void OnClosing(object? sender,FormClosingEventArgs e)
    {
        if(closing){StopServer();return;}
        e.Cancel=true;
        bool busy=false;
        try{if(server!=null&&!server.HasExited){using var s=JsonDocument.Parse(await client.GetStringAsync(origin+"/api/status"));busy=s.RootElement.GetProperty("busy").GetBoolean();}}catch{}
        if(busy&&MessageBox.Show(this,"진행 중인 생성이 중단됩니다. 앱을 종료할까요?","Take Studio 종료",MessageBoxButtons.YesNo,MessageBoxIcon.Question)!=DialogResult.Yes)return;
        closing=true;lifetime.Cancel();StopServer();Close();
    }
    void StopServer()
    {
        if(processJob!=IntPtr.Zero){Native.CloseHandle(processJob);processJob=IntPtr.Zero;}
        try{if(server!=null&&!server.HasExited){server.Kill(true);server.WaitForExit(10000);}}catch(Exception exc){Log("Shutdown: "+exc.Message);}
        server?.Dispose();server=null;
    }
    protected override void Dispose(bool disposing){if(disposing){StopServer();client.Dispose();lifetime.Dispose();mark.Image?.Dispose();}base.Dispose(disposing);}
}

static class Native
{
    [StructLayout(LayoutKind.Sequential)] struct Basic {public long PerProcessUserTimeLimit,PerJobUserTimeLimit;public uint LimitFlags;public UIntPtr MinimumWorkingSetSize,MaximumWorkingSetSize;public uint ActiveProcessLimit;public UIntPtr Affinity;public uint PriorityClass,SchedulingClass;}
    [StructLayout(LayoutKind.Sequential)] struct Io {public ulong ReadOperationCount,WriteOperationCount,OtherOperationCount,ReadTransferCount,WriteTransferCount,OtherTransferCount;}
    [StructLayout(LayoutKind.Sequential)] struct Extended {public Basic BasicLimitInformation;public Io IoInfo;public UIntPtr ProcessMemoryLimit,JobMemoryLimit,PeakProcessMemoryUsed,PeakJobMemoryUsed;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr CreateJobObject(IntPtr attributes,string? name);
    [DllImport("kernel32.dll")] static extern bool SetInformationJobObject(IntPtr job,int info,ref Extended data,uint length);
    [DllImport("kernel32.dll")] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
    public static IntPtr AttachKillOnClose(IntPtr process)
    {
        var job=CreateJobObject(IntPtr.Zero,null);var info=new Extended{BasicLimitInformation=new Basic{LimitFlags=0x2000}};
        if(job==IntPtr.Zero||!SetInformationJobObject(job,9,ref info,(uint)Marshal.SizeOf<Extended>())||!AssignProcessToJobObject(job,process)){if(job!=IntPtr.Zero)CloseHandle(job);throw new IOException("앱 프로세스 관리를 시작하지 못했습니다.");}
        return job;
    }
}
