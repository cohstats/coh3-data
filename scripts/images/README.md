

**Steps by SneakEye:**
- With Janne's Essence.ArchiveViewer I extracted the UI.sga from the archives folder: https://github.com/Janne252/essence-archive-viewer/releases
- Then after modifying the RRTexConverter, I used that to convert the rrtex to png.
 
**Issues:**  
- Sadly I couldn't manage to fix the none square images since my C# skills are non existent ;)
- It currently skips none square images (portraits), but the icons and symbols work fine
- Maybe you can take a look. It has something to do with the width and height being set to the same value, though I don't know which other value to use. It sounds so easy :blush: