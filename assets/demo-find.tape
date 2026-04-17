# mindmark find — semantic search demo
Output assets/mindmark-find.gif

Require mindmark

Set Shell "bash"
Set FontSize 18
Set Width 1000
Set Height 550
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms
Set CursorBlink false

Sleep 500ms

Type "# Search 800 bookmarks with natural language"
Enter
Sleep 600ms

Type "mindmark find 'kubernetes deployment tutorial'"
Sleep 400ms
Enter
Sleep 3s

Type "# Filter by domain"
Enter
Sleep 400ms

Type "mindmark find 'kubernetes' --domain kubernetes.io -k 5"
Sleep 400ms
Enter
Sleep 3s

Type "# Filter by folder"
Enter
Sleep 400ms

Type "mindmark find 'useful tools' --folder Microsoft -k 5"
Sleep 400ms
Enter
Sleep 3s
