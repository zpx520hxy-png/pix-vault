CreateObject("WScript.Shell").Run "python """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\server.py""", 0, False
