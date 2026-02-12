# TexGuardian Demo — VHS tape
# Run: cd demo/ && vhs demo.tape

Output demo.gif
Output demo.mp4

Set Shell "zsh"
Set FontSize 14
Set Width 1280
Set Height 720
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 40ms
Set Padding 20

# Start in the demo project
Type "cd test_run"
Enter
Sleep 500ms

# 1. Start texguardian chat
Type "texguardian chat"
Enter
Sleep 4s

# 2. Run verify — show all issues
Type "/verify"
Enter
Sleep 3s

# 3. Fix figures
Type "/figures fix"
Enter
Sleep 12s

# Approve patches
Type "a"
Enter
Sleep 3s

# 4. Fix tables
Type "/tables fix"
Enter
Sleep 12s

# Approve patches
Type "a"
Enter
Sleep 3s

# 5. Natural language — remove TODOs
Type "Please remove all TODO, FIXME, and XXX comments from the paper"
Enter
Sleep 12s

# Approve patches
Type "a"
Enter
Sleep 3s

# 6. Re-verify — show progress
Type "/verify"
Enter
Sleep 3s

# 7. Exit
Type "/exit"
Enter
Sleep 2s
