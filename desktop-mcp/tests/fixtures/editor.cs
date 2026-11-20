using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

class KeyBlocker : IMessageFilter {
  // Tests run on the owner's live PC: swallow real keyboard input unless started with --accept-keys,
  // so stray keystrokes from the owner never land in the fixture. UIA SetValue does not use key messages.
  public bool PreFilterMessage(ref Message m) { return m.Msg >= 0x100 && m.Msg <= 0x109; }
}

class NoActEditorDlg : Form {
  protected override bool ShowWithoutActivation { get { return true; } }
}

class Editor : Form {
  TextBox box;
  protected override bool ShowWithoutActivation { get { return true; } }

  [STAThread]
  static void Main(string[] args) {
    if (Array.IndexOf(args, "--accept-keys") < 0)
      Application.AddMessageFilter(new KeyBlocker());
    Application.EnableVisualStyles();
    string mode = ArgVal(args, "--mode", "");
    string workdir = ArgVal(args, "--workdir", Path.Combine(Path.GetTempPath(), "turbo-field"));
    string title = ArgVal(args, "--title", "");
    Application.Run(new Editor(mode, workdir, title));
  }

  static string ArgVal(string[] args, string key, string def) {
    for (int i = 0; i < args.Length - 1; i++)
      if (args[i] == key) return args[i + 1];
    return def;
  }

  static string SafeResolve(string root, string relOrName) {
    string r = Path.GetFullPath(root);
    Directory.CreateDirectory(r);
    string candidate = (relOrName ?? "").Trim();
    string p = Path.IsPathRooted(candidate) ? Path.GetFullPath(candidate) : Path.GetFullPath(Path.Combine(r, candidate));
    if (!p.StartsWith(r, StringComparison.OrdinalIgnoreCase))
      throw new InvalidOperationException("Path outside workdir");
    return p;
  }

  public Editor() : this("", Path.Combine(Path.GetTempPath(), "turbo-field"), "") {}

  public Editor(string mode, string workdir, string customTitle) {
    Width = 620; Height = 440;
    StartPosition = FormStartPosition.Manual;
    Location = new Point(80, 80);

    if (mode == "tabs") BuildTabs(workdir);
    else if (mode == "find") BuildFind();
    else if (mode == "save-overwrite") BuildSaveOverwrite(workdir);
    else if (mode == "project") BuildProject(workdir);
    else if (mode == "palette") BuildPalette();
    else if (mode == "richtext") BuildRichText();
    else if (mode == "unsaved") BuildUnsaved();
    else BuildDefault();

    if (!string.IsNullOrEmpty(customTitle))
      Text = customTitle;
  }

  void BuildDefault() {
    Text = "TurboEditor - Untitled";
    var ms = new MenuStrip();
    var file = new ToolStripMenuItem("File");
    var save = new ToolStripMenuItem("Save As...") { ShortcutKeys = Keys.Control | Keys.S };
    save.Click += (s, e) => {
      using (var d = new SaveFileDialog()) {
        d.Filter = "Text|*.txt|All|*.*"; d.Title = "Save As";
        if (d.ShowDialog(this) == DialogResult.OK) {
          File.WriteAllText(d.FileName, box.Text, Encoding.UTF8);
          Text = "TurboEditor - " + Path.GetFileName(d.FileName);
        }
      }
    };
    file.DropDownItems.Add(save); ms.Items.Add(file);
    box = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "Text editor", ScrollBars = ScrollBars.Vertical };
    Controls.Add(box); Controls.Add(ms); MainMenuStrip = ms;
  }

  void BuildTabs(string workdir) {
    Text = "TurboEditor - Tabs";
    var top = new Panel { Dock = DockStyle.Top, Height = 38 };
    var pathBox = new TextBox { Name = "txtSavePath", Left = 8, Top = 8, Width = 310, AccessibleName = "Save path", Text = Path.Combine(workdir, "a.txt") };
    var btnNewTab = new Button { Name = "btnNewTab", Text = "New Tab", Left = 326, Top = 6, Width = 85 };
    var btnSave = new Button { Name = "btnSave", Text = "Save", Left = 418, Top = 6, Width = 80 };
    var status = new TextBox { Name = "txtTabStatus", Left = 504, Top = 8, Width = 96, ReadOnly = true, AccessibleName = "Save status" };
    top.Controls.AddRange(new Control[] { pathBox, btnNewTab, btnSave, status });

    var tabs = new TabControl { Dock = DockStyle.Fill, AccessibleName = "Editor tabs" };
    Func<string, TabPage> makeTab = (title) => {
      var tp = new TabPage(title);
      var tb = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "Text editor", ScrollBars = ScrollBars.Vertical };
      tp.Controls.Add(tb);
      return tp;
    };
    tabs.TabPages.Add(makeTab("Tab 1"));
    int nextTab = 2;
    btnNewTab.Click += (s, e) => {
      var tp = makeTab("Tab " + nextTab++);
      tabs.TabPages.Add(tp);
      tabs.SelectedTab = tp;
    };
    btnSave.Click += (s, e) => {
      var tb = tabs.SelectedTab != null ? tabs.SelectedTab.Controls[0] as TextBox : null;
      if (tb == null) return;
      string outPath = SafeResolve(workdir, pathBox.Text);
      string content = tb.Text.Replace("\r\n", "\n");
      File.WriteAllText(outPath, content, new UTF8Encoding(false));
      status.Text = "Saved " + new FileInfo(outPath).Length + "B";
    };
    Controls.Add(tabs);
    Controls.Add(top);
  }

  void BuildFind() {
    Text = "TurboEditor - Find";
    var history = new Stack<string>();
    var top = new Panel { Dock = DockStyle.Top, Height = 38 };
    var btnFind = new Button { Name = "btnFindReplace", Text = "Find and Replace...", Left = 8, Top = 6, Width = 140 };
    var btnUndo = new Button { Name = "btnUndo", Text = "Undo", Left = 156, Top = 6, Width = 80 };
    var status = new TextBox { Name = "txtFindStatus", Left = 244, Top = 8, Width = 350, ReadOnly = true, AccessibleName = "Status" };
    top.Controls.AddRange(new Control[] { btnFind, btnUndo, status });

    box = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "Text editor", ScrollBars = ScrollBars.Vertical };
    btnUndo.Click += (s, e) => {
      if (history.Count > 0) {
        box.Text = history.Pop();
        status.Text = "Undone";
      }
    };
    btnFind.Click += (s, e) => {
      BeginInvoke((Action)(() => {
        var dlg = new NoActEditorDlg { Text = "Find and Replace", Width = 360, Height = 170, StartPosition = FormStartPosition.Manual, Location = new Point(140, 140) };
        var txtFind = new TextBox { Name = "txtFind", Left = 90, Top = 14, Width = 240, AccessibleName = "Find what" };
        var txtRep = new TextBox { Name = "txtReplace", Left = 90, Top = 46, Width = 240, AccessibleName = "Replace with" };
        var btnRepAll = new Button { Name = "btnReplaceAll", Text = "Replace All", Left = 90, Top = 84, Width = 110 };
        var btnClose = new Button { Name = "btnCloseDlg", Text = "Close", Left = 210, Top = 84, Width = 100 };
        btnRepAll.Click += (_s, _e) => {
          if (!string.IsNullOrEmpty(txtFind.Text)) {
            history.Push(box.Text);
            box.Text = box.Text.Replace(txtFind.Text, txtRep.Text);
            status.Text = "Replaced";
          }
        };
        btnClose.Click += (_s, _e) => { dlg.Close(); };
        dlg.Controls.AddRange(new Control[] {
          new Label { Text = "Find", Left = 10, Top = 16, Width = 75 }, txtFind,
          new Label { Text = "Replace", Left = 10, Top = 48, Width = 75 }, txtRep,
          btnRepAll, btnClose
        });
        dlg.Show(this);
      }));
    };
    Controls.Add(box);
    Controls.Add(top);
  }

  void BuildSaveOverwrite(string workdir) {
    Text = "TurboEditor - Overwrite";
    string existing = SafeResolve(workdir, "existing.txt");
    File.WriteAllText(existing, "OLD CONTENT", new UTF8Encoding(false));
    var top = new Panel { Dock = DockStyle.Top, Height = 38 };
    var pathBox = new TextBox { Name = "txtPath", Left = 8, Top = 8, Width = 320, AccessibleName = "Save path", Text = existing };
    var btnSave = new Button { Name = "btnSave", Text = "Save", Left = 336, Top = 6, Width = 80 };
    var status = new TextBox { Name = "txtStatus", Left = 424, Top = 8, Width = 170, ReadOnly = true, AccessibleName = "Save status" };
    top.Controls.AddRange(new Control[] { pathBox, btnSave, status });
    box = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "Text editor" };

    btnSave.Click += (s, e) => {
      string outPath = SafeResolve(workdir, pathBox.Text);
      if (File.Exists(outPath)) {
        BeginInvoke((Action)(() => {
          var dlg = new NoActEditorDlg { Text = "Confirm Overwrite", Width = 360, Height = 150, StartPosition = FormStartPosition.Manual, Location = new Point(150, 150) };
          var lbl = new TextBox { Left = 12, Top = 14, Width = 320, ReadOnly = true, AccessibleName = "Prompt", Text = Path.GetFileName(outPath) + " already exists. Replace it?" };
          var yes = new Button { Name = "btnYes", Text = "Yes", Left = 120, Top = 60, Width = 90 };
          var no = new Button { Name = "btnNo", Text = "No", Left = 220, Top = 60, Width = 90 };
          yes.Click += (_s, _e) => {
            File.WriteAllText(outPath, box.Text.Replace("\r\n", "\n"), new UTF8Encoding(false));
            status.Text = "Overwritten";
            dlg.Close();
          };
          no.Click += (_s, _e) => { status.Text = "Cancelled"; dlg.Close(); };
          dlg.Controls.AddRange(new Control[] { lbl, yes, no });
          dlg.Show(this);
        }));
      } else {
        File.WriteAllText(outPath, box.Text.Replace("\r\n", "\n"), new UTF8Encoding(false));
        status.Text = "Saved";
      }
    };
    Controls.Add(box);
    Controls.Add(top);
  }

  void BuildProject(string workdir) {
    Text = "TurboEditor - Project";
    Directory.CreateDirectory(workdir);
    var top = new Panel { Dock = DockStyle.Top, Height = 38 };
    var fname = new TextBox { Name = "txtFilename", Left = 8, Top = 8, Width = 200, AccessibleName = "File name", Text = "hello.py" };
    var btnNew = new Button { Name = "btnNewFile", Text = "New File", Left = 216, Top = 6, Width = 90 };
    var btnSave = new Button { Name = "btnSaveFile", Text = "Save File", Left = 314, Top = 6, Width = 90 };
    var status = new TextBox { Name = "txtProjStatus", Left = 412, Top = 8, Width = 185, ReadOnly = true, AccessibleName = "Project status" };
    top.Controls.AddRange(new Control[] { fname, btnNew, btnSave, status });
    box = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "Code editor", ScrollBars = ScrollBars.Vertical };
    btnNew.Click += (s, e) => { box.Text = ""; status.Text = "Editing " + fname.Text; };
    btnSave.Click += (s, e) => {
      string outPath = SafeResolve(workdir, fname.Text);
      File.WriteAllText(outPath, box.Text.Replace("\r\n", "\n"), new UTF8Encoding(false));
      status.Text = "Saved " + Path.GetFileName(outPath);
    };
    Controls.Add(box);
    Controls.Add(top);
  }

  void BuildPalette() {
    Text = "TurboEditor - Palette";
    bool wordWrap = false;
    var top = new Panel { Dock = DockStyle.Top, Height = 38 };
    var btnPal = new Button { Name = "btnPalette", Text = "Command Palette...", Left = 8, Top = 6, Width = 150 };
    var status = new TextBox { Name = "txtWrapStatus", Left = 168, Top = 8, Width = 260, ReadOnly = true, AccessibleName = "Word wrap status", Text = "Word Wrap: Off" };
    top.Controls.AddRange(new Control[] { btnPal, status });
    box = new TextBox { Multiline = true, Dock = DockStyle.Fill, WordWrap = false, AccessibleName = "Text editor", Text = "Long sample line for word wrap check." };
    btnPal.Click += (s, e) => {
      BeginInvoke((Action)(() => {
        var dlg = new NoActEditorDlg { Text = "Command Palette", Width = 360, Height = 230, StartPosition = FormStartPosition.Manual, Location = new Point(150, 130) };
        var lb = new ListBox { Name = "lstCmds", Left = 10, Top = 10, Width = 324, Height = 120, AccessibleName = "Commands" };
        lb.Items.AddRange(new object[] { "Toggle Word Wrap", "Uppercase Text", "Clear Editor" });
        var runBtn = new Button { Name = "btnRunCmd", Text = "Run Command", Left = 10, Top = 140, Width = 130 };
        runBtn.Click += (_s, _e) => {
          string sel = lb.SelectedItem != null ? lb.SelectedItem.ToString() : "";
          if (sel == "Toggle Word Wrap") {
            wordWrap = !wordWrap;
            box.WordWrap = wordWrap;
            status.Text = "Word Wrap: " + (wordWrap ? "On" : "Off");
          } else if (sel == "Uppercase Text") {
            box.Text = box.Text.ToUpperInvariant();
          } else if (sel == "Clear Editor") {
            box.Text = "";
          }
          dlg.Close();
        };
        dlg.Controls.AddRange(new Control[] { lb, runBtn });
        dlg.Show(this);
      }));
    };
    Controls.Add(box);
    Controls.Add(top);
  }

  void BuildRichText() {
    Text = "TurboEditor - RichText";
    var top = new Panel { Dock = DockStyle.Top, Height = 38 };
    var target = new TextBox { Name = "txtTargetWord", Left = 8, Top = 8, Width = 140, AccessibleName = "Target word", Text = "world" };
    var btnBold = new Button { Name = "btnBold", Text = "Bold", Left = 156, Top = 6, Width = 75 };
    var status = new TextBox { Name = "txtFormatStatus", Left = 240, Top = 8, Width = 355, ReadOnly = true, AccessibleName = "Formatting status", Text = "Normal" };
    top.Controls.AddRange(new Control[] { target, btnBold, status });
    var rtb = new RichTextBox { Name = "rtbEditor", Dock = DockStyle.Fill, AccessibleName = "Rich editor", Font = new Font("Segoe UI", 10) };
    btnBold.Click += (s, e) => {
      string w = target.Text ?? "";
      int idx = !string.IsNullOrEmpty(w) ? rtb.Text.IndexOf(w, StringComparison.Ordinal) : -1;
      if (idx >= 0) {
        rtb.Select(idx, w.Length);
        rtb.SelectionFont = new Font(rtb.Font, FontStyle.Bold);
        status.Text = "Bold: " + w;
      } else {
        rtb.SelectionFont = new Font(rtb.Font, FontStyle.Bold);
        status.Text = "Bold: selection";
      }
    };
    Controls.Add(rtb);
    Controls.Add(top);
  }

  void BuildUnsaved() {
    Text = "TurboEditor - Unsaved";
    bool allowClose = false;
    box = new TextBox { Multiline = true, Dock = DockStyle.Fill, AccessibleName = "Text editor" };
    Controls.Add(box);
    FormClosing += (s, e) => {
      if (!allowClose && !string.IsNullOrEmpty(box.Text)) {
        e.Cancel = true;
        BeginInvoke((Action)(() => {
          var dlg = new NoActEditorDlg { Text = "Unsaved Changes", Width = 380, Height = 150, StartPosition = FormStartPosition.Manual, Location = new Point(150, 150) };
          var msg = new TextBox { Left = 12, Top = 14, Width = 340, ReadOnly = true, AccessibleName = "Prompt", Text = "Save changes before closing?" };
          var bSave = new Button { Name = "btnSaveClose", Text = "Save", Left = 20, Top = 60, Width = 95 };
          var bDont = new Button { Name = "btnDontSave", Text = "Don't Save", Left = 125, Top = 60, Width = 110 };
          var bCancel = new Button { Name = "btnCancelClose", Text = "Cancel", Left = 245, Top = 60, Width = 95 };
          bDont.Click += (_s, _e) => { allowClose = true; dlg.Close(); Close(); };
          bSave.Click += (_s, _e) => { allowClose = true; dlg.Close(); Close(); };
          bCancel.Click += (_s, _e) => { dlg.Close(); };
          dlg.Controls.AddRange(new Control[] { msg, bSave, bDont, bCancel });
          dlg.Show(this);
        }));
      }
    };
  }
}
