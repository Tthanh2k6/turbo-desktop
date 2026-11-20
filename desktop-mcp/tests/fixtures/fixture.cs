using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;

class KeyBlocker : IMessageFilter {
  // Tests run on the owner's live PC: swallow real keyboard input unless started with --accept-keys,
  // so stray keystrokes from the owner never land in the fixture. UIA SetValue does not use key messages.
  public bool PreFilterMessage(ref Message m) { return m.Msg >= 0x100 && m.Msg <= 0x109; }
}

class Fixture : Form {
  [STAThread]
  static void Main(string[] args) {
    if (Array.IndexOf(args, "--accept-keys") < 0)
      Application.AddMessageFilter(new KeyBlocker());
    Application.EnableVisualStyles();
    string mode = ArgVal(args, "--mode", "");
    string workdir = ArgVal(args, "--workdir", Path.Combine(Path.GetTempPath(), "turbo-field"));
    string title = ArgVal(args, "--title", "");
    double splashSec = 0;
    double.TryParse(ArgVal(args, "--splash", "0"), System.Globalization.NumberStyles.Float,
      System.Globalization.CultureInfo.InvariantCulture, out splashSec);
    if (splashSec > 0) {
      Application.Run(new SplashRunner(splashSec, () => new Fixture(mode, workdir, title)));
      return;
    }
    Application.Run(new Fixture(mode, workdir, title));
  }

  static string ArgVal(string[] args, string key, string def) {
    for (int i = 0; i < args.Length - 1; i++)
      if (args[i] == key) return args[i + 1];
    return def;
  }

  protected override bool ShowWithoutActivation { get { return true; } }

  public Fixture() : this("", Path.Combine(Path.GetTempPath(), "turbo-field"), "") {}

  public Fixture(string mode, string workdir, string customTitle) {
    StartPosition = FormStartPosition.Manual;
    Location = new Point(60, 60);
    ShowInTaskbar = true;
    if (mode == "explorer" || mode == "vfiles") BuildExplorer(workdir);
    else if (mode == "biglist") BuildBigList();
    else if (mode == "prefs") BuildPrefs();
    else if (mode == "display") BuildDisplay();
    else if (mode == "settings" || mode == "config") BuildSettings();
    else if (mode == "timer") BuildTimer();
    else if (mode == "docview") BuildDocView();
    else BuildDefault(mode);
    if (!string.IsNullOrEmpty(customTitle)) Text = customTitle;
  }

  void BuildDefault(string mode) {
    Text = "TurboFixture"; Width = 460; Height = 420;
    var l1 = new Label { Text = "Full name", Left = 10, Top = 12, Width = 90 };
    var name = new TextBox { Name = "txtName", Left = 110, Top = 10, Width = 300, AccessibleName = "Full name" };
    var l2 = new Label { Text = "Country", Left = 10, Top = 46, Width = 90 };
    var country = new ComboBox { Name = "cboCountry", Left = 110, Top = 44, Width = 300, DropDownStyle = ComboBoxStyle.DropDownList, AccessibleName = "Country" };
    country.Items.AddRange(new object[] { "Vietnam", "Japan", "Germany" });
    var agree = new CheckBox { Name = "chkAgree", Text = "I agree to terms", Left = 110, Top = 80, Width = 300 };
    var l3 = new Label { Text = "Password", Left = 10, Top = 114, Width = 90 };
    var pwd = new TextBox { Name = "txtPwd", Left = 110, Top = 112, Width = 300, UseSystemPasswordChar = true, AccessibleName = "Password" };
    var submit = new Button { Name = "btnSubmit", Text = "Submit", Left = 110, Top = 150, Width = 120 };
    var clear = new Button { Name = "btnClear", Text = "Clear", Left = 240, Top = 150, Width = 120 };
    var result = new Label { Name = "lblResult", Text = "", Left = 10, Top = 190, Width = 420, Height = 40 };
    var shortBox = new TextBox { Name = "txtShort", Left = 110, Top = 280, Width = 300, MaxLength = 10, AccessibleName = "Short code" };
    var counter = new Button { Name = "btnCount", Text = "Count 0", Left = 110, Top = 240, Width = 120 };
    int n = 0;
    counter.Click += (s, e) => { n++; counter.Text = "Count " + n; };
    submit.Click += (s, e) => { result.Text = "Submitted: " + name.Text + " / " + country.Text + " / agree=" + agree.Checked; };
    clear.Click += (s, e) => { name.Text = ""; country.SelectedIndex = -1; agree.Checked = false; result.Text = "Cleared"; };
    Controls.AddRange(new Control[] { l1, name, l2, country, agree, l3, pwd, submit, clear, result, counter, shortBox });
    if (mode == "ime") {
      Text = "TurboFixture - IME";
      var imeStatus = new TextBox { Name = "txtImeStatus", Left = 110, Top = 320, Width = 300, ReadOnly = true, AccessibleName = "IME result" };
      name.TextChanged += (s, e) => { imeStatus.Text = "Value: " + name.Text + " (len=" + name.Text.Length + ")"; };
      Controls.Add(imeStatus);
    }
  }

  static string SafeResolve(string root, string rel) {
    string r = Path.GetFullPath(root);
    string p = Path.GetFullPath(Path.Combine(r, (rel ?? "").Trim()));
    if (!p.StartsWith(r, StringComparison.OrdinalIgnoreCase))
      throw new InvalidOperationException("Path outside workdir");
    return p;
  }

  void BuildExplorer(string workdir) {
    Text = "TurboFiles"; Width = 620; Height = 460;
    string root = Path.GetFullPath(workdir);
    Directory.CreateDirectory(root);

    var targetName = new TextBox { Name = "txtItemName", Left = 12, Top = 12, Width = 220, AccessibleName = "Item name" };
    var btnNewFolder = new Button { Name = "btnNewFolder", Text = "New Folder", Left = 240, Top = 10, Width = 95 };
    var btnRename = new Button { Name = "btnRename", Text = "Rename", Left = 342, Top = 10, Width = 80 };
    var btnNewFile = new Button { Name = "btnNewFile", Text = "New File", Left = 428, Top = 10, Width = 85 };
    var btnDetails = new Button { Name = "btnDetails", Text = "Details View", Left = 518, Top = 10, Width = 85 };
    var status = new TextBox { Name = "txtExplorerStatus", Left = 12, Top = 42, Width = 590, ReadOnly = true, AccessibleName = "View status", Text = "View: List" };

    var lv = new ListView { Name = "lvFiles", Left = 12, Top = 74, Width = 590, Height = 330, View = View.List, FullRowSelect = true, AccessibleName = "File list" };
    lv.Columns.Add("Name", 260);
    lv.Columns.Add("Type", 120);
    lv.Columns.Add("Size", 120);

    Action refresh = () => {
      lv.Items.Clear();
      foreach (var d in Directory.GetDirectories(root).OrderBy(x => x)) {
        var it = new ListViewItem(new[] { Path.GetFileName(d), "Folder", "" });
        lv.Items.Add(it);
      }
      foreach (var f in Directory.GetFiles(root).OrderBy(x => x)) {
        var fi = new FileInfo(f);
        var it = new ListViewItem(new[] { fi.Name, "File", fi.Length + " B" });
        lv.Items.Add(it);
      }
      status.Text = "View: " + lv.View + " | Items: " + lv.Items.Count;
    };

    btnNewFolder.Click += (s, e) => {
      string nm = string.IsNullOrWhiteSpace(targetName.Text) ? "New Folder" : targetName.Text.Trim();
      Directory.CreateDirectory(SafeResolve(root, nm));
      refresh();
    };
    btnRename.Click += (s, e) => {
      string newNm = targetName.Text.Trim();
      if (lv.SelectedItems.Count > 0 && !string.IsNullOrEmpty(newNm)) {
        string oldNm = lv.SelectedItems[0].Text;
        string src = SafeResolve(root, oldNm);
        string dst = SafeResolve(root, newNm);
        if (Directory.Exists(src)) Directory.Move(src, dst);
        else if (File.Exists(src)) File.Move(src, dst);
        refresh();
      }
    };
    btnNewFile.Click += (s, e) => {
      string nm = string.IsNullOrWhiteSpace(targetName.Text) ? "note.txt" : targetName.Text.Trim();
      File.WriteAllText(SafeResolve(root, nm), "created by virtual explorer");
      refresh();
    };
    btnDetails.Click += (s, e) => {
      lv.View = View.Details;
      refresh();
    };

    Controls.AddRange(new Control[] { targetName, btnNewFolder, btnRename, btnNewFile, btnDetails, status, lv });
    refresh();
  }

  void BuildBigList() {
    Text = "TurboBigList"; Width = 540; Height = 460;
    var items = Enumerable.Range(0, 200)
      .Select(i => new { Name = string.Format("file_{0:000}.txt", i), Size = ((i * 73) % 9000) + 100 })
      .ToList();
    bool sorted = false;
    var btnSort = new Button { Name = "btnSortSize", Text = "Sort by Size", Left = 12, Top = 10, Width = 120 };
    var lblTotal = new TextBox { Name = "txtTotal", Left = 144, Top = 12, Width = 370, ReadOnly = true, AccessibleName = "Total items", Text = "Total: 200 items (unsorted)" };
    var lb = new ListBox { Name = "lstBig", Left = 12, Top = 44, Width = 502, Height = 365, AccessibleName = "Files" };

    Action populate = () => {
      lb.BeginUpdate();
      lb.Items.Clear();
      var seq = sorted ? items.OrderByDescending(x => x.Size).ThenBy(x => x.Name) : items.AsEnumerable();
      foreach (var it in seq)
        lb.Items.Add(string.Format("{0} ({1} B)", it.Name, it.Size));
      lb.EndUpdate();
    };
    btnSort.Click += (s, e) => {
      sorted = true;
      populate();
      lblTotal.Text = "Total: 200 items (sorted by size desc)";
    };
    populate();
    Controls.AddRange(new Control[] { btnSort, lblTotal, lb });
  }

  void BuildPrefs() {
    Text = "TurboPrefs"; Width = 440; Height = 220;
    int speed = 5;
    var lbl = new Label { Text = "Current speed", Left = 12, Top = 18, Width = 110 };
    var cur = new TextBox { Name = "txtCurrentSpeed", Left = 130, Top = 15, Width = 140, ReadOnly = true, AccessibleName = "Current speed", Text = speed.ToString() };
    var btnOpen = new Button { Name = "btnOpenPrefs", Text = "Mouse Preferences...", Left = 12, Top = 55, Width = 180 };
    btnOpen.Click += (s, e) => {
      BeginInvoke((Action)(() => {
        var dlg = new NoActForm { Text = "Mouse Preferences", Width = 380, Height = 190, StartPosition = FormStartPosition.Manual, Location = new Point(120, 140) };
        var sl = new TrackBar { Name = "trkSpeed", Minimum = 1, Maximum = 10, Value = speed, Left = 16, Top = 20, Width = 240, AccessibleName = "Double-click speed" };
        var valBox = new TextBox { Name = "txtSliderVal", Left = 270, Top = 24, Width = 70, ReadOnly = true, AccessibleName = "Speed value", Text = speed.ToString() };
        sl.ValueChanged += (_s, _e) => { valBox.Text = sl.Value.ToString(); };
        var ok = new Button { Name = "btnOk", Text = "OK", Left = 150, Top = 95, Width = 90 };
        var cancel = new Button { Name = "btnCancel", Text = "Cancel", Left = 250, Top = 95, Width = 90 };
        ok.Click += (_s, _e) => { speed = sl.Value; cur.Text = speed.ToString(); dlg.Close(); };
        cancel.Click += (_s, _e) => { dlg.Close(); };
        dlg.Controls.AddRange(new Control[] { sl, valBox, ok, cancel });
        dlg.Show(this);
      }));
    };
    Controls.AddRange(new Control[] { lbl, cur, btnOpen });
  }

  void BuildDisplay() {
    Text = "TurboDisplay"; Width = 440; Height = 220;
    Controls.AddRange(new Control[] {
      new Label { Text = "Scale", Left = 12, Top = 16, Width = 110 },
      new TextBox { Name = "txtScale", Left = 130, Top = 14, Width = 260, ReadOnly = true, AccessibleName = "Scale", Text = "100%" },
      new Label { Text = "Resolution", Left = 12, Top = 52, Width = 110 },
      new TextBox { Name = "txtRes", Left = 130, Top = 50, Width = 260, ReadOnly = true, AccessibleName = "Resolution", Text = "1920 x 1080" },
      new Label { Text = "Orientation", Left = 12, Top = 88, Width = 110 },
      new TextBox { Name = "txtOrient", Left = 130, Top = 86, Width = 260, ReadOnly = true, AccessibleName = "Orientation", Text = "Landscape" },
    });
  }

  void BuildSettings() {
    Text = "TurboConfig"; Width = 480; Height = 300;
    var search = new TextBox { Name = "txtSearch", Left = 12, Top = 12, Width = 440, AccessibleName = "Search config" };
    var bt = new CheckBox { Name = "chkBluetooth", Text = "Bluetooth", Left = 16, Top = 54, Width = 200, Checked = true, AccessibleName = "Bluetooth" };
    var wifi = new CheckBox { Name = "chkWifi", Text = "Wi-Fi", Left = 16, Top = 84, Width = 200, Checked = true, AccessibleName = "Wi-Fi" };
    var dark = new CheckBox { Name = "chkDark", Text = "Dark Mode", Left = 16, Top = 114, Width = 200, Checked = false, AccessibleName = "Dark Mode" };
    var status = new TextBox { Name = "txtBtStatus", Left = 12, Top = 160, Width = 440, ReadOnly = true, AccessibleName = "Bluetooth status", Text = "Bluetooth: On" };
    bt.CheckedChanged += (s, e) => { status.Text = "Bluetooth: " + (bt.Checked ? "On" : "Off"); };
    search.TextChanged += (s, e) => {
      string q = (search.Text ?? "").Trim().ToLowerInvariant();
      bt.Visible = string.IsNullOrEmpty(q) || "bluetooth".Contains(q);
      wifi.Visible = string.IsNullOrEmpty(q) || "wi-fi".Contains(q) || "wifi".Contains(q);
      dark.Visible = string.IsNullOrEmpty(q) || "dark mode".Contains(q);
    };
    Controls.AddRange(new Control[] { search, bt, wifi, dark, status });
  }

  void BuildTimer() {
    Text = "TurboTimer"; Width = 460; Height = 260;
    var dur = new TextBox { Name = "txtDuration", Left = 12, Top = 14, Width = 180, AccessibleName = "Timer duration", Text = "1 min" };
    var add = new Button { Name = "btnAddTimer", Text = "Add Timer", Left = 202, Top = 12, Width = 100 };
    var start = new Button { Name = "btnStartTimer", Text = "Start", Left = 12, Top = 52, Width = 95 };
    var del = new Button { Name = "btnDeleteTimer", Text = "Delete", Left = 116, Top = 52, Width = 95 };
    var status = new TextBox { Name = "txtTimerStatus", Left = 12, Top = 96, Width = 420, ReadOnly = true, AccessibleName = "Timer status", Text = "Ready" };
    add.Click += (s, e) => { status.Text = "Timer created: " + dur.Text; };
    start.Click += (s, e) => { status.Text = "Running: " + dur.Text; };
    del.Click += (s, e) => { status.Text = "Deleted"; };
    Controls.AddRange(new Control[] { dur, add, start, del, status });
  }

  void BuildDocView() {
    Text = "TurboDocView"; Width = 540; Height = 360;
    Panel cur = new Panel { Dock = DockStyle.Fill };
    Controls.Add(cur);
    for (int i = 0; i < 6; i++) {
      var next = new Panel { Dock = DockStyle.Fill, Padding = new Padding(4) };
      cur.Controls.Add(next);
      cur = next;
    }
    var heading = new TextBox { Name = "txtHeading", Left = 10, Top = 12, Width = 440, ReadOnly = true, AccessibleName = "Heading", Text = "Example Domain" };
    var body = new TextBox {
      Name = "txtBody", Left = 10, Top = 48, Width = 440, Height = 180, Multiline = true, ReadOnly = true,
      AccessibleName = "Document body",
      Text = "This domain is for use in illustrative examples in documents.\r\nYou may use this domain in literature without prior coordination."
    };
    cur.Controls.AddRange(new Control[] { heading, body });
  }
}

class NoActForm : Form {
  protected override bool ShowWithoutActivation { get { return true; } }
}

class SplashRunner : ApplicationContext {
  Form main;
  public SplashRunner(double sec, Func<Form> factory) {
    var splash = new NoActForm { Text = "TurboSplash - Loading", Width = 320, Height = 140, StartPosition = FormStartPosition.Manual, Location = new Point(100, 100) };
    splash.Controls.Add(new Label { Text = "Loading TurboFixture...", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter });
    splash.Show();
    var t = new System.Windows.Forms.Timer { Interval = Math.Max(500, (int)(sec * 1000)) };
    t.Tick += (s, e) => {
      t.Stop();
      t.Dispose();
      main = factory();
      main.FormClosed += (_s, _e) => ExitThread();
      main.Show();
      splash.Close();
    };
    t.Start();
  }
}
