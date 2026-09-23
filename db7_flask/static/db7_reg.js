(function () {
  "use strict";

  var state = {
    connected: false,
    md: 1,
    fpga: "",
    bus: "rx",
    map: { rx: [], tx: [], xadc: [] },
    selected: null,
    values: {},
  };

  var $ = function (id) { return document.getElementById(id); };

  function log(msg) {
    var el = $("log");
    var ts = new Date().toISOString().substr(11, 12);
    el.textContent = ts + "  " + msg + "\n" + el.textContent;
  }

  function hex32(v) {
    var n = (Number(v) >>> 0);
    var s = n.toString(16).toUpperCase();
    while (s.length < 8) s = "0" + s;
    return "0x" + s;
  }

  function hexAddr(v) {
    var s = Number(v).toString(16).toUpperCase();
    while (s.length < 3) s = "0" + s;
    return "0x" + s;
  }

  function keyOf(reg) {
    return state.bus + ":" + reg.index;
  }

  function busy(on) {
    document.body.classList.toggle("busy", !!on);
  }

  function api(path, body) {
    var opts = { headers: { "Accept": "application/json" } };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok || data.ok === false) {
          throw new Error(data.error || ("HTTP " + res.status));
        }
        return data;
      });
    });
  }

  function setConnected(on, fwHex, err) {
    state.connected = !!on;
    $("led").className = "led" + (err ? " err" : on ? " on" : "");
    $("fw-label").textContent = err
      ? err
      : on
        ? ("FW " + (fwHex || "?"))
        : "not connected";
    $("btn-disconnect").disabled = !on;
    $("btn-connect").textContent = on ? "Reconnect" : "Connect";
  }

  function currentRegs() {
    return state.map[state.bus] || [];
  }

  function applyFilter() {
    var q = ($("filter").value || "").toLowerCase();
    var rows = document.querySelectorAll("#reg-table tbody tr");
    for (var i = 0; i < rows.length; i++) {
      var hay = rows[i].getAttribute("data-filter") || "";
      rows[i].classList.toggle("hidden", q && hay.indexOf(q) === -1);
    }
  }

  function decodedCell(row) {
    var parts = [];
    function pack(label, obj) {
      if (!obj) return;
      var keys = Object.keys(obj);
      if (!keys.length) return;
      parts.push(label + " " + keys.map(function (k) {
        return k + "=" + obj[k];
      }).join(" "));
    }
    pack("A", row.decoded_a);
    pack("B", row.decoded_b);
    return parts.join(" · ");
  }

  function renderTable() {
    var tbody = document.querySelector("#reg-table tbody");
    tbody.innerHTML = "";
    var regs = currentRegs();
    for (var i = 0; i < regs.length; i++) {
      var reg = regs[i];
      var stored = state.values[keyOf(reg)];
      var tr = document.createElement("tr");
      tr.setAttribute("data-index", String(reg.index));
      tr.setAttribute(
        "data-filter",
        (reg.index + " " + reg.name + " " + reg.hw_addr_hex).toLowerCase()
      );
      if (state.selected && state.selected.index === reg.index) {
        tr.className = "selected";
      }
      var aHex = stored ? stored.side_a.hex : "—";
      var bHex = stored ? stored.side_b.hex : "—";
      var dec = stored ? decodedCell(stored) : (reg.note || "");
      tr.innerHTML =
        '<td class="num">' + reg.index + "</td>" +
        '<td class="name">' + reg.name + "</td>" +
        '<td class="num hex">' + hexAddr(reg.hw_addr) + "</td>" +
        '<td class="hex">' + aHex + "</td>" +
        '<td class="hex">' + bHex + "</td>" +
        "<td>" + dec + "</td>";
      tr.addEventListener("click", onRowClick);
      tbody.appendChild(tr);
    }
    applyFilter();
    updateWriteHint();
  }

  function onRowClick(ev) {
    var tr = ev.currentTarget;
    var idx = Number(tr.getAttribute("data-index"));
    var regs = currentRegs();
    for (var i = 0; i < regs.length; i++) {
      if (regs[i].index === idx) {
        selectReg(regs[i]);
        break;
      }
    }
  }

  function selectReg(reg) {
    state.selected = reg;
    $("sel-title").textContent = reg.index + "  " + reg.name;
    $("sel-note").textContent =
      "index " + reg.index +
      " · hw " + hexAddr(reg.hw_addr) +
      (reg.writable ? " · writable" : " · read-only") +
      (reg.note ? " — " + reg.note : "");
    var stored = state.values[keyOf(reg)];
    if (stored) {
      $("write-value").value = stored.side_a.hex;
    }
    renderTable();
    renderBits();
    renderFields(stored);
  }

  function parseValue() {
    var text = $("write-value").value.trim();
    if (!text) return 0;
    if (/^0x/i.test(text)) return parseInt(text, 16) >>> 0;
    if (/^0b/i.test(text)) return parseInt(text.slice(2), 2) >>> 0;
    return parseInt(text, 10) >>> 0;
  }

  function setValue(v) {
    $("write-value").value = hex32(v);
    renderBits();
  }

  function renderBits() {
    var grid = $("bit-grid");
    grid.innerHTML = "";
    var val = parseValue();
    var fields = (state.selected && state.selected.fields) || [];
    var fieldBits = {};
    for (var f = 0; f < fields.length; f++) {
      for (var b = fields[f].lsb; b <= fields[f].msb; b++) fieldBits[b] = true;
    }
    for (var i = 31; i >= 0; i--) {
      var on = ((val >>> i) & 1) === 1;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "bit" + (on ? " on" : "") + (fieldBits[i] ? " field" : "");
      btn.innerHTML = '<span class="n">' + i + "</span><span>" + (on ? "1" : "0") + "</span>";
      btn.setAttribute("data-bit", String(i));
      btn.addEventListener("click", function (ev) {
        var bit = Number(ev.currentTarget.getAttribute("data-bit"));
        setValue(parseValue() ^ ((1 << bit) >>> 0));
      });
      grid.appendChild(btn);
    }
  }

  function renderFields(stored) {
    var box = $("field-list");
    box.innerHTML = "";
    var fields = (state.selected && state.selected.fields) || [];
    if (!fields.length) return;
    for (var i = 0; i < fields.length; i++) {
      var f = fields[i];
      var aVal = "";
      var bVal = "";
      if (stored) {
        var fa = stored.fields_a.filter(function (x) { return x.name === f.name; })[0];
        var fb = stored.fields_b.filter(function (x) { return x.name === f.name; })[0];
        if (fa) aVal = fa.hex;
        if (fb) bVal = fb.hex;
      }
      var row = document.createElement("div");
      row.className = "field-row";
      var range = f.lsb === f.msb ? String(f.lsb) : (f.msb + ":" + f.lsb);
      row.innerHTML =
        "<span>" + f.name + " [" + range + "]" +
        (f.note ? "  " + f.note : "") + "</span>" +
        "<span>A " + (aVal || "—") + "  B " + (bVal || "—") + "</span>";
      var aim = document.createElement("button");
      aim.type = "button";
      aim.textContent = "aim";
      aim.title = "Set aim bit to LSB (db7_modregval -a)";
      (function (lsb) {
        aim.addEventListener("click", function (ev) {
          ev.stopPropagation();
          $("write-aim").value = String(lsb);
          $("write-value").value = "1";
        });
      })(f.lsb);
      row.appendChild(aim);
      box.appendChild(row);
    }
  }

  function storeRow(row) {
    var k = row.register.bus + ":" + row.register.index;
    state.values[k] = row;
  }

  function updateWriteHint() {
    var fpga = state.fpga ? ("FPGA " + state.fpga) : "FPGA broadcast";
    $("write-hint").textContent = fpga + " · MD " + state.md +
      (state.selected && !state.selected.writable ? " · TX/XADC is read-only" : "");
  }

  function connect(ev) {
    if (ev) ev.preventDefault();
    var controlhub = $("controlhub-ip").value.trim();
    var ppr = $("ppr-ip").value.trim();
    localStorage.setItem("db7_controlhub_ip", controlhub);
    localStorage.setItem("db7_ppr_ip", ppr);
    busy(true);
    api("/api/connect", { controlhub_ip: controlhub, ppr_ip: ppr })
      .then(function (data) {
        setConnected(true, data.fw_version_hex);
        log("Connected  ControlHub " + data.controlhub_ip +
            "  TilePPr " + data.ppr_ip + "  FW " + data.fw_version_hex);
      })
      .catch(function (err) {
        setConnected(false, null, err.message);
        log("Connect failed: " + err.message);
      })
      .then(function () { busy(false); });
  }

  function disconnect() {
    api("/api/disconnect", {}).then(function () {
      setConnected(false);
      log("Disconnected");
    });
  }

  function readSelected() {
    if (!state.selected) {
      log("Select a register first");
      return;
    }
    busy(true);
    api("/api/read", {
      md: state.md,
      bus: state.bus,
      register: state.selected.index,
    }).then(function (row) {
      storeRow(row);
      $("write-value").value = row.side_a.hex;
      renderTable();
      renderFields(row);
      log("Read " + row.register.name +
          "  A " + row.side_a.hex + "  B " + row.side_b.hex);
    }).catch(function (err) {
      log("Read failed: " + err.message);
    }).then(function () { busy(false); });
  }

  function readAll() {
    busy(true);
    log("Reading all " + state.bus + " registers on MD " + state.md + "…");
    api("/api/read_all", { md: state.md, bus: state.bus })
      .then(function (data) {
        for (var i = 0; i < data.rows.length; i++) storeRow(data.rows[i]);
        renderTable();
        if (state.selected) {
          renderFields(state.values[keyOf(state.selected)]);
        }
        log("Read " + data.rows.length + " " + data.bus + " registers");
      })
      .catch(function (err) {
        log("Read all failed: " + err.message);
      })
      .then(function () { busy(false); });
  }

  function writeReg(ev) {
    ev.preventDefault();
    if (!state.selected) {
      log("Select a register first");
      return;
    }
    if (state.bus !== "rx") {
      log("Only ConfigBus RX registers are writable");
      return;
    }
    var body = {
      md: state.md,
      fpga: state.fpga,
      bus: "rx",
      register: state.selected.index,
      value: $("write-value").value.trim(),
      mask: $("write-mask").value.trim() || "0",
      aim: $("write-aim").value.trim(),
      sync: $("write-sync").checked,
      bcid: $("write-bcid").value.trim(),
    };
    busy(true);
    api("/api/write", body)
      .then(function (row) {
        storeRow(row);
        renderTable();
        renderFields(row);
        log("Wrote " + row.register.name + " = " + row.wrote.value_hex +
            "  readback A " + row.side_a.hex + "  B " + row.side_b.hex);
      })
      .catch(function (err) {
        log("Write failed: " + err.message);
      })
      .then(function () { busy(false); });
  }

  function syncClear() {
    busy(true);
    api("/api/sync_clear", {})
      .then(function () { log("SyncClear"); })
      .catch(function (err) { log("SyncClear failed: " + err.message); })
      .then(function () { busy(false); });
  }

  function wireSeg(selector, attr, key) {
    var buttons = document.querySelectorAll(selector);
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function (ev) {
        var btn = ev.currentTarget;
        for (var j = 0; j < buttons.length; j++) buttons[j].classList.remove("active");
        btn.classList.add("active");
        state[key] = btn.getAttribute(attr) || "";
        if (key === "md") state.md = Number(state.md);
        if (key === "bus") {
          state.selected = null;
          $("sel-title").textContent = "No register selected";
          $("sel-note").textContent = "Click a row.";
          $("field-list").innerHTML = "";
          renderTable();
        } else {
          updateWriteHint();
        }
      });
    }
  }

  $("conn-form").addEventListener("submit", connect);
  $("btn-disconnect").addEventListener("click", disconnect);
  $("btn-read").addEventListener("click", readSelected);
  $("btn-read-all").addEventListener("click", readAll);
  $("btn-sync-clear").addEventListener("click", syncClear);
  $("write-form").addEventListener("submit", writeReg);
  $("write-value").addEventListener("input", renderBits);
  $("filter").addEventListener("input", applyFilter);
  wireSeg(".md-btn", "data-md", "md");
  wireSeg(".fpga-btn", "data-fpga", "fpga");
  wireSeg(".tab", "data-bus", "bus");

  var savedHub = localStorage.getItem("db7_controlhub_ip");
  var savedPpr = localStorage.getItem("db7_ppr_ip");
  if (savedHub) $("controlhub-ip").value = savedHub;
  if (savedPpr) $("ppr-ip").value = savedPpr;

  renderBits();

  api("/api/registers").then(function (map) {
    state.map = map;
    renderTable();
    log("Loaded register map from " + map.source);
  }).catch(function (err) {
    log("Failed to load register map: " + err.message);
  });

  fetch("/api/status").then(function (r) { return r.json(); }).then(function (s) {
    if (s.connected) setConnected(true, s.fw_version_hex);
  });
})();
