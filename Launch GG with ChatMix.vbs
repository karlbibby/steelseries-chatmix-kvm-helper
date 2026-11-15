Option Explicit
Dim shell, files, folder, config, python, helper, reader
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
folder = files.GetParentFolderName(WScript.ScriptFullName)
config = files.BuildPath(folder, "pythonw-path.txt")
If Not files.FileExists(config) Then
    MsgBox "Run Install.ps1 first. Alternatively launch gg_chatmix_helper.py with Python.", 48, "GG ChatMix helper"
    WScript.Quit 1
End If
Set reader = files.OpenTextFile(config, 1)
python = Trim(reader.ReadAll)
reader.Close
If Not files.FileExists(python) Then
    MsgBox "Python could not be found. Run Install.ps1 again after repairing Python.", 48, "GG ChatMix helper"
    WScript.Quit 1
End If
helper = files.BuildPath(folder, "gg_chatmix_helper.py")
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & helper & Chr(34), 0, False
