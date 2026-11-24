/*
 * Click a Mermaid diagram to open it in a viewer you can zoom and pan.
 *
 *   - Mouse wheel (or pinch on a trackpad) zooms toward the cursor; drag to pan; double-click zooms in.
 *   - The + / - / fit buttons do the same from the toolbar, and the keys +, -, 0 and the arrow keys work too.
 *   - Esc, the close button, or a click on the backdrop closes the viewer.
 *   - It opens fitted to the screen width, aligned to the top, when the diagram is tall, so a vertical chart starts out
 *     readable instead of shrinking to fit the height. A wide diagram opens fitted whole.
 *
 * Each diagram also gets Copy, SVG and PNG buttons (top right on hover, and in the viewer toolbar). Copy puts a PNG on
 * the clipboard, falling back to the SVG text where the browser refuses images.
 *
 * The theme renders each diagram into a closed shadow root, so the SVG is out of reach by default. This script wraps
 * `attachShadow` to keep a reference to each diagram's root as the theme creates it, which is what lets the buttons read
 * the SVG, and otherwise only touches the wrapper element (div.mermaid), moving and scaling it with a CSS transform.
 * It must therefore load after the theme bundle but before Mermaid finishes loading, which is how extra_javascript
 * behaves. Styles are in stylesheets/mermaid-expand.css. Handlers are delegated from `document`, so they keep working
 * across the theme's instant page navigation.
 */
(function () {
  "use strict";

  var PADDING = 16; // px, matches the padding in mermaid-expand.css
  var MARGIN = 32; // px kept free around the diagram when fitting it
  var MAX_INITIAL = 3; // largest scale a diagram opens at
  var MAX_SCALE = 10;
  var DRAG_THRESHOLD = 4; // px of movement before a press counts as a drag rather than a click
  var STEP = 1.4; // zoom factor for the buttons and keys
  var PAN_STEP = 80; // px moved per arrow-key press

  var scriptUrl = document.currentScript && document.currentScript.src; // fonts are located relative to this file
  var roots = new WeakMap(); // div.mermaid wrapper -> its (closed) shadow root
  var nativeAttachShadow = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function (init) {
    var root = nativeAttachShadow.call(this, init);
    if (this.classList && this.classList.contains("mermaid")) roots.set(this, root);
    return root;
  };

  var view = null; // { host, spacer, backdrop, toolbar, width, height, scale, x, y, minScale, fit, drag, moved }


  // ---- Export: copy and download -------------------------------------------------------------------------------

  var SVG_NS = "http://www.w3.org/2000/svg";
  var VAR_PATTERN = /var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)/g;
  var MAX_PNG_SIDE = 8192; // px
  var PNG_SCALE = 2;

  // Site fonts to embed in exported SVG and PNG files, as { file, style } entries under assets/fonts/. This site uses the
  // theme's default font, so there is nothing to embed.
  var FONT_FILES = [];
  var fontCss = null;

  function toBase64(buffer) {
    var bytes = new Uint8Array(buffer);
    var binary = "";
    for (var i = 0; i < bytes.length; i += 0x8000) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(binary);
  }

  // @font-face rules with the site font inlined. An SVG opened on its own, or drawn into a PNG, cannot load the page's
  // fonts, so without this its labels fall back to a wider font and spill out of their boxes. Resolves to "" if the
  // fonts cannot be fetched, in which case the export still works with the fallback font.
  function embeddedFonts() {
    if (!fontCss) {
      fontCss = Promise.all(
        FONT_FILES.map(function (font) {
          var url = new URL("../assets/fonts/" + font.file, scriptUrl).href;
          return fetch(url)
            .then(function (response) {
              if (!response.ok) throw new Error("Font not found.");
              return response.arrayBuffer();
            })
            .then(function (buffer) {
              return (
                '@font-face{font-family:"SiteFont";font-style:' + font.style + ";font-weight:300 800;" +
                'src:url("data:font/woff2;base64,' + toBase64(buffer) + '") format("woff2");}'
              );
            });
        })
      )
        .then(function (rules) {
          return rules.join("");
        })
        .catch(function () {
          return "";
        });
    }
    return fontCss;
  }

  // The diagram as a standalone SVG string, with the theme's CSS variables replaced by their current values and the
  // site font embedded so it looks the same outside the page. Resolves to { text, width, height, background }, or
  // rejects if the diagram has not rendered.
  function exportData(host) {
    return embeddedFonts().then(function (css) {
      return buildExport(host, css);
    });
  }

  function buildExport(host, css) {
    var root = roots.get(host);
    var svg = root && root.querySelector("svg");
    if (!svg) throw new Error("Diagram not ready.");

    var box = svg.viewBox && svg.viewBox.baseVal;
    var rect = svg.getBoundingClientRect();
    var width = Math.ceil((box && box.width) || rect.width);
    var height = Math.ceil((box && box.height) || rect.height);
    var themed = getComputedStyle(document.body);
    var background = themed.getPropertyValue("--md-default-bg-color").trim() || "#ffffff";

    var clone = svg.cloneNode(true);
    clone.setAttribute("xmlns", SVG_NS);
    clone.setAttribute("width", width);
    clone.setAttribute("height", height);
    clone.style.maxWidth = "";
    clone.style.background = background;
    if (css) {
      var style = document.createElementNS(SVG_NS, "style");
      style.textContent = css;
      clone.insertBefore(style, clone.firstChild);
    }

    var text = new XMLSerializer().serializeToString(clone).replace(VAR_PATTERN, function (match, name, fallback) {
      return themed.getPropertyValue(name).trim() || (fallback || "").trim() || match;
    });
    return { text: text, width: width, height: height, background: background };
  }

  function svgBlob(data) {
    return new Blob([data.text], { type: "image/svg+xml;charset=utf-8" });
  }

  // The labels are HTML inside a foreignObject. Chromium and Firefox keep the canvas exportable when the SVG is loaded
  // from a data: URL, where a blob: URL would taint it. Safari taints it either way, so PNG fails there and Copy falls
  // back to the SVG text.
  function pngBlob(data) {
    return new Promise(function (resolve, reject) {
      var url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(data.text);
      var image = new Image();
      image.onload = function () {
        var scale = Math.min(PNG_SCALE, MAX_PNG_SIDE / Math.max(data.width, data.height));
        var canvas = document.createElement("canvas");
        canvas.width = Math.round(data.width * scale);
        canvas.height = Math.round(data.height * scale);
        var context = canvas.getContext("2d");
        context.fillStyle = data.background;
        context.fillRect(0, 0, canvas.width, canvas.height);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        try {
          canvas.toBlob(function (blob) {
            if (blob) resolve(blob);
            else reject(new Error("The browser produced no image."));
          }, "image/png");
        } catch (error) {
          reject(error);
        }
      };
      image.onerror = function () {
        reject(new Error("The browser could not draw the diagram."));
      };
      image.src = url;
    });
  }

  // A file name from the heading above the diagram, e.g. "company-matching-flow".
  function fileBase(host) {
    var node = host.closest(".mermaid-frame") || host;
    for (var sibling = node.previousElementSibling; sibling; sibling = sibling.previousElementSibling) {
      if (/^H[1-4]$/.test(sibling.tagName)) {
        var slug = sibling.textContent
          .replace(/¶/g, "")
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "");
        if (slug) return slug;
      }
    }
    return "diagram";
  }

  function download(blob, name) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  function copyImage(host) {
    if (!navigator.clipboard) return Promise.reject(new Error("Clipboard unavailable."));
    var data = exportData(host);
    // Hand the clipboard a promise for the image, so the write starts inside the click and keeps its permission.
    var asImage = window.ClipboardItem
      ? navigator.clipboard.write([new ClipboardItem({ "image/png": data.then(pngBlob) })]).then(function () {
          return "Copied";
        })
      : Promise.reject(new Error("Images are not supported."));
    return asImage.catch(function () {
      return data.then(function (d) {
        return navigator.clipboard.writeText(d.text).then(function () {
          return "Copied SVG";
        });
      });
    });
  }

  var ACTIONS = [
    {
      label: "Copy",
      title: "Copy the diagram as an image",
      run: copyImage,
    },
    {
      label: "SVG",
      title: "Download the diagram as an SVG file",
      run: function (host) {
        return exportData(host).then(function (data) {
          download(svgBlob(data), fileBase(host) + ".svg");
          return "Saved";
        });
      },
    },
    {
      label: "PNG",
      title: "Download the diagram as a PNG file",
      run: function (host) {
        return exportData(host)
          .then(pngBlob)
          .then(function (blob) {
            download(blob, fileBase(host) + ".png");
            return "Saved";
          });
      },
    },
  ];

  // Buttons for one diagram. `extraClass` lets the same buttons sit in the page and in the viewer toolbar.
  function actionButtons(host, extraClass) {
    return ACTIONS.map(function (action) {
      var el = document.createElement("button");
      el.type = "button";
      el.className = "mermaid-action " + extraClass;
      el.textContent = action.label;
      el.title = action.title;
      el.addEventListener("click", function (event) {
        event.stopPropagation();
        action.run(host).then(
          function (message) {
            flash(el, action.label, message);
          },
          function () {
            flash(el, action.label, "Failed");
          }
        );
      });
      return el;
    });
  }

  function flash(el, label, message) {
    el.textContent = message;
    clearTimeout(el._reset);
    el._reset = setTimeout(function () {
      el.textContent = label;
    }, 1500);
  }

  function clamp(value, low, high) {
    return Math.min(Math.max(value, low), high);
  }

  function apply() {
    view.host.style.transform = "translate(" + view.x + "px, " + view.y + "px) scale(" + view.scale + ")";
  }

  // Scale and place the diagram as it first opens, and again for the fit button.
  function fit() {
    var availableWidth = window.innerWidth - MARGIN;
    var availableHeight = window.innerHeight - MARGIN;
    var fitWidth = availableWidth / view.width;
    var fitWhole = Math.min(fitWidth, availableHeight / view.height);
    var tall = view.height * fitWidth > availableHeight;

    view.minScale = fitWhole * 0.5;
    view.scale = clamp(tall ? fitWidth : fitWhole, view.minScale, MAX_INITIAL);
    view.x = (window.innerWidth - view.width * view.scale) / 2;
    view.y = tall ? MARGIN / 2 : (window.innerHeight - view.height * view.scale) / 2;
    apply();
  }

  // Zoom by `factor`, keeping the screen point (px, py) fixed.
  function zoomAt(factor, px, py) {
    var scale = clamp(view.scale * factor, view.minScale, MAX_SCALE);
    var ratio = scale / view.scale;
    view.x = px - (px - view.x) * ratio;
    view.y = py - (py - view.y) * ratio;
    view.scale = scale;
    apply();
  }

  function zoomCentered(factor) {
    zoomAt(factor, window.innerWidth / 2, window.innerHeight / 2);
  }

  function button(label, text, handler) {
    var el = document.createElement("button");
    el.type = "button";
    el.className = "mermaid-tool";
    el.setAttribute("aria-label", label);
    el.title = label;
    el.textContent = text;
    el.addEventListener("click", function (event) {
      event.stopPropagation();
      handler();
    });
    return el;
  }

  function close() {
    if (!view) return;
    var host = view.host;
    host.classList.remove("mermaid-expanded");
    host.style.removeProperty("width");
    host.style.removeProperty("height");
    host.style.removeProperty("transform");
    view.spacer.remove();
    view.backdrop.remove();
    view.toolbar.remove();
    document.documentElement.classList.remove("mermaid-expand-open");
    view = null;
  }

  function open(host) {
    var rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    // Hold the diagram's place in the page, since the wrapper is about to leave the flow.
    var spacer = document.createElement("div");
    spacer.style.height = rect.height + "px";
    host.parentNode.insertBefore(spacer, host);

    var backdrop = document.createElement("div");
    backdrop.className = "mermaid-backdrop";

    var toolbar = document.createElement("div");
    toolbar.className = "mermaid-toolbar";
    toolbar.append.apply(toolbar, actionButtons(host, "mermaid-action--toolbar"));
    toolbar.append(
      button("Zoom in", "+", function () {
        zoomCentered(STEP);
      }),
      button("Zoom out", "−", function () {
        zoomCentered(1 / STEP);
      }),
      button("Fit to screen", "⤢", fit),
      button("Close", "×", close)
    );
    document.body.append(backdrop, toolbar);

    view = {
      host: host,
      spacer: spacer,
      backdrop: backdrop,
      toolbar: toolbar,
      width: rect.width + 2 * PADDING,
      height: rect.height + 2 * PADDING,
      scale: 1,
      x: 0,
      y: 0,
      minScale: 0.1,
      drag: null,
      moved: false,
    };
    host.style.width = view.width + "px";
    host.style.height = view.height + "px";
    host.classList.add("mermaid-expanded");
    document.documentElement.classList.add("mermaid-expand-open");
    fit();
  }

  // Dragging works from the diagram or the backdrop, so you can grab anywhere.
  function startDrag(event) {
    if (!view || event.button > 0) return;
    view.drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
    view.moved = false;
    event.target.setPointerCapture(event.pointerId);
  }

  function moveDrag(event) {
    if (!view || !view.drag || view.drag.id !== event.pointerId) return;
    var dx = event.clientX - view.drag.x;
    var dy = event.clientY - view.drag.y;
    if (!view.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    view.moved = true;
    view.x += dx;
    view.y += dy;
    view.drag.x = event.clientX;
    view.drag.y = event.clientY;
    view.host.classList.add("mermaid-dragging");
    apply();
  }

  function endDrag(event) {
    if (!view || !view.drag || view.drag.id !== event.pointerId) return;
    view.drag = null;
    view.host.classList.remove("mermaid-dragging");
  }

  function diagramFrom(event) {
    // The wrapper holds a shadow root, so a click inside the SVG is retargeted to the wrapper itself.
    var target = event.target;
    return target && target.closest ? target.closest("div.mermaid") : null;
  }

  document.addEventListener("click", function (event) {
    var host = diagramFrom(event);
    if (!view) {
      if (host) open(host);
    } else if (event.target === view.backdrop && !view.moved) {
      close();
    }
  });

  document.addEventListener("dblclick", function (event) {
    if (view && diagramFrom(event) === view.host) zoomAt(2, event.clientX, event.clientY);
  });

  document.addEventListener("pointerdown", function (event) {
    if (view && (event.target === view.host || event.target === view.backdrop)) startDrag(event);
  });
  document.addEventListener("pointermove", moveDrag);
  document.addEventListener("pointerup", endDrag);
  document.addEventListener("pointercancel", endDrag);

  document.addEventListener(
    "wheel",
    function (event) {
      if (!view) return;
      event.preventDefault();
      // Line-based wheels report small deltas; trackpad pinch arrives as ctrl+wheel with fine-grained ones.
      var delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
      zoomAt(Math.exp(-delta * (event.ctrlKey ? 0.01 : 0.0015)), event.clientX, event.clientY);
    },
    { passive: false }
  );

  document.addEventListener("keydown", function (event) {
    if (view) {
      var handled = true;
      switch (event.key) {
        case "Escape":
          close();
          break;
        case "+":
        case "=":
          zoomCentered(STEP);
          break;
        case "-":
          zoomCentered(1 / STEP);
          break;
        case "0":
          fit();
          break;
        case "ArrowLeft":
          view.x += PAN_STEP;
          apply();
          break;
        case "ArrowRight":
          view.x -= PAN_STEP;
          apply();
          break;
        case "ArrowUp":
          view.y += PAN_STEP;
          apply();
          break;
        case "ArrowDown":
          view.y -= PAN_STEP;
          apply();
          break;
        default:
          handled = false;
      }
      if (handled) event.preventDefault();
    } else if ((event.key === "Enter" || event.key === " ") && event.target.matches && event.target.matches("div.mermaid")) {
      event.preventDefault();
      open(event.target);
    }
  });

  window.addEventListener("resize", close);

  // Make rendered diagrams reachable by keyboard. They appear after the page loads, so watch for them.
  function markFocusable(root) {
    root.querySelectorAll("div.mermaid:not([data-mermaid-ready])").forEach(function (host) {
      host.setAttribute("data-mermaid-ready", "");
      host.setAttribute("tabindex", "0");
      host.setAttribute("role", "button");
      host.setAttribute("aria-label", "Open diagram viewer");

      // Wrap the diagram so the copy and download buttons can float over it. Moving the wrapper element keeps its
      // shadow root.
      var frame = document.createElement("div");
      frame.className = "mermaid-frame";
      var actions = document.createElement("div");
      actions.className = "mermaid-actions";
      actions.append.apply(actions, actionButtons(host, ""));
      host.parentNode.insertBefore(frame, host);
      frame.append(actions, host);
    });
  }

  new MutationObserver(function () {
    markFocusable(document);
  }).observe(document.documentElement, { childList: true, subtree: true });
  markFocusable(document);
})();
