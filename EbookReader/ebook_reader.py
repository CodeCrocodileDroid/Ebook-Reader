import wx
import wx.lib.newevent
import os
import threading
import pyttsx3

# ---------------------------------------------------------------------------
# Offline Services
# ---------------------------------------------------------------------------

class TTSService:
    """Handles Offline Text-to-Speech using pyttsx3."""
    def __init__(self):
        self.engine = None
        self.is_speaking = False
        try:
            self.engine = pyttsx3.init()
        except Exception as e:
            print(f"TTS Init failed: {e}")

    def speak(self, text):
        if not self.engine:
            return
        
        if self.is_speaking:
            self.stop()

        self.is_speaking = True
        
        # TTS engine block the loop, so we run it in a thread
        threading.Thread(target=self._speak_thread, args=(text,)).start()

    def _speak_thread(self, text):
        try:
            # We need a new engine instance for the thread or careful locking
            # pyttsx3 is tricky with threads. 
            # Safe approach: Run the loop inside the thread.
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS Error: {e}")
        finally:
            self.is_speaking = False

    def stop(self):
        if self.engine and self.is_speaking:
            self.engine.stop()
            self.is_speaking = False

# ---------------------------------------------------------------------------
# GUI Components
# ---------------------------------------------------------------------------

class NotesPanel(wx.Panel):
    """Sidebar panel for User Notes (Replacements Chat)."""
    def __init__(self, parent):
        super().__init__(parent)
        
        # Layout
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(self, label="My Notes")
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        sizer.Add(title, 0, wx.ALL, 10)

        # Notes Area
        self.notes_area = wx.TextCtrl(self, style=wx.TE_MULTILINE)
        sizer.Add(self.notes_area, 1, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        save_btn = wx.Button(self, label="Save Notes (Local)")
        save_btn.Bind(wx.EVT_BUTTON, self.on_save)
        btn_sizer.Add(save_btn, 0, wx.RIGHT, 5)
        
        clear_btn = wx.Button(self, label="Clear")
        clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)
        btn_sizer.Add(clear_btn, 0)

        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        self.SetSizer(sizer)
        
        self.notes_area.SetValue("Use this space to take notes on your book.\n\nNotes are kept in memory for this session.")

    def on_save(self, event):
        # In a real app, save to a file/db
        wx.MessageBox("Notes saved to memory!", "Success", wx.OK)

    def on_clear(self, event):
        self.notes_area.Clear()


class ReaderPanel(wx.Panel):
    """Main reading area."""
    def __init__(self, parent, tts_service):
        super().__init__(parent)
        self.tts_service = tts_service
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Toolbar
        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        open_btn = wx.Button(self, label="📂 Open File")
        open_btn.Bind(wx.EVT_BUTTON, self.on_open_file)
        toolbar_sizer.Add(open_btn, 0, wx.ALL, 5)

        self.read_btn = wx.Button(self, label="🔊 Read Aloud")
        self.read_btn.Bind(wx.EVT_BUTTON, self.on_read_aloud)
        toolbar_sizer.Add(self.read_btn, 0, wx.ALL, 5)

        stop_btn = wx.Button(self, label="⏹ Stop")
        stop_btn.Bind(wx.EVT_BUTTON, self.on_stop_read)
        toolbar_sizer.Add(stop_btn, 0, wx.ALL, 5)
        
        self.title_lbl = wx.StaticText(self, label="No Book Loaded")
        toolbar_sizer.Add(self.title_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        
        sizer.Add(toolbar_sizer, 0, wx.EXPAND)

        # Text Area
        self.text_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_NOHIDESEL | wx.TE_RICH2)
        font = wx.Font(12, wx.FONTFAMILY_ROMAN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Georgia")
        self.text_ctrl.SetFont(font)
        self.text_ctrl.SetMargins(20, 20)
        
        # Search Bar
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_lbl = wx.StaticText(self, label="Search:")
        self.search_box = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search_box.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        search_btn = wx.Button(self, label="Find Next")
        search_btn.Bind(wx.EVT_BUTTON, self.on_search)

        search_sizer.Add(search_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        search_sizer.Add(self.search_box, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        search_sizer.Add(search_btn, 0, wx.RIGHT, 5)

        sizer.Add(self.text_ctrl, 1, wx.EXPAND)
        sizer.Add(search_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(sizer)

    def on_open_file(self, event):
        with wx.FileDialog(self, "Open text file", wildcard="Text files (*.txt)|*.txt",
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = fileDialog.GetPath()
            try:
                with open(pathname, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.text_ctrl.SetValue(content)
                    self.title_lbl.SetLabel(os.path.basename(pathname))
            except IOError:
                wx.LogError("Cannot open file.")

    def get_content(self):
        return self.text_ctrl.GetValue()

    def on_read_aloud(self, event):
        # Read selection or full text from cursor
        selection = self.text_ctrl.GetStringSelection()
        if selection:
            self.tts_service.speak(selection)
        else:
            # Read from current insertion point roughly
            full_text = self.text_ctrl.GetValue()
            pos = self.text_ctrl.GetInsertionPoint()
            self.tts_service.speak(full_text[pos:])

    def on_stop_read(self, event):
        self.tts_service.stop()

    def on_search(self, event):
        query = self.search_box.GetValue()
        if not query:
            return
        
        full_text = self.text_ctrl.GetValue().lower()
        query = query.lower()
        
        # Simple search from current cursor
        start_pos = self.text_ctrl.GetInsertionPoint()
        found_pos = full_text.find(query, start_pos + 1)
        
        if found_pos == -1:
             # Wrap around
             found_pos = full_text.find(query, 0)

        if found_pos != -1:
            self.text_ctrl.SetInsertionPoint(found_pos)
            self.text_ctrl.SetSelection(found_pos, found_pos + len(query))
            self.text_ctrl.SetFocus()
        else:
            wx.MessageBox("Text not found.", "Search", wx.OK | wx.ICON_INFORMATION)


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Offline Reader (wxPython + pyttsx3)", size=(1000, 700))

        self.tts_service = TTSService()

        # Splitter to hold Reader and Notes
        self.splitter = wx.SplitterWindow(self)

        # Panels
        self.reader_panel = ReaderPanel(self.splitter, self.tts_service)
        self.notes_panel = NotesPanel(self.splitter)

        # Split
        self.splitter.SplitVertically(self.reader_panel, self.notes_panel)
        self.splitter.SetMinimumPaneSize(250)
        self.splitter.SetSashGravity(0.7) # 70% reader, 30% notes

        self.CreateStatusBar()
        self.SetStatusText("Ready - Offline Mode")

if __name__ == '__main__':
    app = wx.App()
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
