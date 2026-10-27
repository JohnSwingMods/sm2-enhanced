# Aiutante "musica" del menu in gioco: legge da Windows cosa sta suonando (qualsiasi app: Spotify, browser...) e lo
# comanda. Resta aperto e risponde una riga JSON per ogni comando ricevuto su stdin: info | foto | play | next | prev | vol | vol+ | vol-.
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
Function Await($t, $r) { $asTask.MakeGenericMethod($r).Invoke($null, @($t)).Result }
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IInputStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
$asStream = [System.IO.WindowsRuntimeStreamExtensions].GetMethod('AsStreamForRead', [type[]]@([Windows.Storage.Streams.IInputStream]))
# volume della SOLA app che suona (mixer di Windows, come "Mixer volume"): Core Audio via C#
Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices; using System.Diagnostics; using System.Collections.Generic;
namespace SpideyAudio {
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumerator {}
  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator { int NotImpl1(); [PreserveSig] int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice dev); }
  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice { [PreserveSig] int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
  [Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionManager2 { int NotImpl1(); int NotImpl2(); [PreserveSig] int GetSessionEnumerator(out IAudioSessionEnumerator e); }
  [Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionEnumerator { [PreserveSig] int GetCount(out int n); [PreserveSig] int GetSession(int i, out IAudioSessionControl2 s); }
  [Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioSessionControl2 {
    int NotImpl0(); [PreserveSig] int GetDisplayName([MarshalAs(UnmanagedType.LPWStr)] out string s);
    int NotImpl1(); int NotImpl2(); int NotImpl3(); int NotImpl4(); int NotImpl5(); int NotImpl6(); int NotImpl7();
    [PreserveSig] int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string s);
    [PreserveSig] int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string s);
    [PreserveSig] int GetProcessId(out int pid);
  }
  [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface ISimpleAudioVolume {
    [PreserveSig] int SetMasterVolume(float v, ref Guid ctx); [PreserveSig] int GetMasterVolume(out float v);
    [PreserveSig] int SetMute(bool m, ref Guid ctx); [PreserveSig] int GetMute(out bool m);
  }
  public static class Vol {
    static List<ISimpleAudioVolume> Sessioni(string nome) {
      var out_ = new List<ISimpleAudioVolume>();
      var en = (IMMDeviceEnumerator)(new MMDeviceEnumerator());
      IMMDevice dev; if (en.GetDefaultAudioEndpoint(0, 1, out dev) != 0) return out_;
      Guid iid = typeof(IAudioSessionManager2).GUID; object o;
      if (dev.Activate(ref iid, 23, IntPtr.Zero, out o) != 0) return out_;
      IAudioSessionEnumerator se; ((IAudioSessionManager2)o).GetSessionEnumerator(out se);
      int n; se.GetCount(out n);
      for (int i = 0; i < n; i++) {
        IAudioSessionControl2 c; se.GetSession(i, out c);
        int pid; c.GetProcessId(out pid);
        string pn = "";
        try { pn = Process.GetProcessById(pid).ProcessName; } catch { }
        if (pid != 0 && pn.Length > 0 && (pn.Equals(nome, StringComparison.OrdinalIgnoreCase) || pn.ToLower().Contains(nome.ToLower()) || nome.ToLower().Contains(pn.ToLower())))
          out_.Add((ISimpleAudioVolume)c);
      }
      return out_;
    }
    public static float Get(string nome) { foreach (var v in Sessioni(nome)) { float f; v.GetMasterVolume(out f); return f; } return -1; }
    public static float Set(string nome, float x) {
      x = Math.Max(0f, Math.Min(1f, x)); Guid g = Guid.Empty; bool ok = false;
      foreach (var v in Sessioni(nome)) { v.SetMasterVolume(x, ref g); ok = true; }
      return ok ? x : -1;
    }
  }
}
"@
Function NomeApp($s) {  # "SpotifyAB.SpotifyMusic_...!Spotify" -> Spotify, "Spotify.exe" -> Spotify, "Chrome" -> Chrome
    $id = [string]$s.SourceAppUserModelId
    if ($id -match '!([^!]+)$') { return $matches[1] }
    if ($id -match '([^\\]+)\.exe$') { return $matches[1] }
    return $id
}
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$mgr = $null
while ($true) {
    $cmd = [Console]::In.ReadLine()
    if ($null -eq $cmd) { break }
    try {
        if ($null -eq $mgr) { $mgr = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]) }
        $s = $mgr.GetCurrentSession()
        if ($null -eq $s) { '{"sessione":false}'; continue }
        switch ($cmd) {
            'info' {
                $p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
                $tl = $s.GetTimelineProperties()
                @{ sessione = $true; app = $s.SourceAppUserModelId; titolo = $p.Title; artista = $p.Artist; album = $p.AlbumTitle
                   stato = [string]$s.GetPlaybackInfo().PlaybackStatus; pos = $tl.Position.TotalSeconds; durata = $tl.EndTime.TotalSeconds
                   foto = [bool]$p.Thumbnail } | ConvertTo-Json -Compress
            }
            'foto' {
                $p = Await ($s.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])
                if ($null -eq $p.Thumbnail) { '{"foto":null}' } else {
                    $st = Await ($p.Thumbnail.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
                    # da PowerShell il flusso WinRT non si converte da solo: AsStreamForRead chiamato via reflection
                    $net = $asStream.Invoke($null, @($st))
                    $ms = New-Object System.IO.MemoryStream
                    $net.CopyTo($ms)
                    $buf = $ms.ToArray()
                    @{ foto = [Convert]::ToBase64String($buf); tipo = '' } | ConvertTo-Json -Compress
                }
            }
            'vol' { @{ vol = [SpideyAudio.Vol]::Get((NomeApp $s)) } | ConvertTo-Json -Compress }
            'vol+' { $v = [SpideyAudio.Vol]::Get((NomeApp $s)); @{ vol = $(if ($v -lt 0) { -1 } else { [SpideyAudio.Vol]::Set((NomeApp $s), $v + 0.05) }) } | ConvertTo-Json -Compress }
            'vol-' { $v = [SpideyAudio.Vol]::Get((NomeApp $s)); @{ vol = $(if ($v -lt 0) { -1 } else { [SpideyAudio.Vol]::Set((NomeApp $s), $v - 0.05) }) } | ConvertTo-Json -Compress }
            'play' { $null = Await ($s.TryTogglePlayPauseAsync()) ([bool]); '{"ok":true}' }
            'next' { $null = Await ($s.TrySkipNextAsync()) ([bool]); '{"ok":true}' }
            'prev' { $null = Await ($s.TrySkipPreviousAsync()) ([bool]); '{"ok":true}' }
            default { '{"errore":"comando"}' }
        }
    } catch { @{ errore = $_.Exception.Message } | ConvertTo-Json -Compress }
}
