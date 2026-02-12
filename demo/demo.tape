# TexGuardian Demo — VHS tape
# Run: cd demo/ && vhs demo.tape
# Produces demo.gif and demo.mp4

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

# Ensure TinyTeX is on PATH
Type "export PATH=$HOME/Library/TinyTeX/bin/universal-darwin:$PATH"
Enter
Sleep 500ms

# Start in the demo project
Type "cd test_run"
Enter
Sleep 500ms

# 1. Start texguardian chat — welcome panel with paper stats
Type "texguardian chat"
Enter
Sleep 4s

# 2. Set venue with natural language — downloads ICLR template files
Type "/venue let's use the ICLR template file for our paper"
Enter
Sleep 10s

# 3. Run the full 7-step review pipeline
Type "/review full"
Enter
Sleep 15s

# Approve figure patches when prompted
Type "a"
Enter
Sleep 5s

# Approve table patches when prompted
Type "a"
Enter
Sleep 5s

# Wait for visual verification loop (Steps 6-7)
Sleep 20s

# If second round patches are prompted, approve
Type "a"
Enter
Sleep 10s

# Show the final result
Type "/bash open build/demo_paper.pdf"
Enter
Sleep 3s

# Exit
Type "/exit"
Enter
Sleep 2s
