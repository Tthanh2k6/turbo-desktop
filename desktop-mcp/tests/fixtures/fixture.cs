using System;
using System.Drawing;
using System.Windows.Forms;

class KeyBlocker : IMessageFilter {
  // Tests run on the owner's live PC: swallow real keyboard input unless started with --accept-keys,
  // so stray keystrokes from the owner never land in the fixture. UIA SetValue does not use key messages.
  public bool PreFilterMessage(ref Message m) { return m.Msg >= 0x100 && m.Msg <= 0x109; }
}

class Fixture : Form {
  [STAThread] static void Main(string[] args) { if (Array.IndexOf(args, "--accept-keys") < 0) Application.AddMessageFilter(new KeyBlocker());  Application.EnableVisualStyles(); Application.Run(new Fixture()); }
  protected override bool ShowWithoutActivation { get { return true; } }
  public Fixture() {
    Text = "TurboFixture"; Width = 460; Height = 420; StartPosition = FormStartPosition.Manual; Location = new Point(60, 60); ShowInTaskbar = true;
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
  }
}
