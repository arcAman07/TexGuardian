# TexGuardian Demo — VHS tape (1 minute)
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

# 1. Start texguardian chat — welcome panel with paper stats
Type "texguardian chat"
Enter
Sleep 4s

# 2. Set venue — downloads ICLR 2025 style files
Type "/venue ICLR 2025"
Enter
Sleep 10s

# 3. Fix figures — LLM patches overflow issues
Type "/figures fix"
Enter
Sleep 12s

# Approve patches
Type "a"
Enter
Sleep 3s

# 4. Fix tables — LLM converts hline to booktabs
Type "/tables fix"
Enter
Sleep 12s

# Approve patches
Type "a"
Enter
Sleep 3s

# 5. Compile — build the final PDF
Type "/compile"
Enter
Sleep 8s

# 6. Open the compiled PDF
Type "/bash open build/demo_paper.pdf"
Enter
Sleep 3s

# 7. Exit
Type "/exit"
Enter
Sleep 2s
