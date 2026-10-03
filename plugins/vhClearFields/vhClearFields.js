"use strict";
(() => {
  const api = window.PluginApi;
  const { React, patch, GQL, hooks, components, libraries } = api;
  const { useState } = React;
  const { Modal, Button, Form } = libraries.Bootstrap;
  const { useIntl } = libraries.Intl;
  const { faExclamationTriangle } = libraries.FontAwesomeSolid;
  const { Icon } = components;
  const h = React.createElement;

  const PLUGIN_ID = "vhClearFields";
  const TASK_NAME = "Clear scene fields";

  // input/empty mirror FIELD_CLEARS in vhClearFields.py (used for the synchronous scene-page path)
  const FIELDS = [
    { key: "title", setting: "clearTitle", label: "Title", input: "title", empty: () => "" },
    { key: "urls", setting: "clearUrls", label: "URLs", input: "urls", empty: () => [] },
    { key: "date", setting: "clearDate", label: "Date", input: "date", empty: () => null },
    { key: "director", setting: "clearDirector", label: "Director", input: "director", empty: () => "" },
    { key: "performers", setting: "clearPerformers", label: "Performers", input: "performer_ids", empty: () => [] },
    { key: "studio", setting: "clearStudio", label: "Studio", input: "studio_id", empty: () => null },
    { key: "details", setting: "clearDetails", label: "Details", input: "details", empty: () => "" },
    { key: "stashIds", setting: "clearStashIds", label: "Stash IDs", input: "stash_ids", empty: () => [] },
    { key: "code", setting: "clearCode", label: "Studio code", input: "code", empty: () => "" },
  ];

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // Mirrors Stash's ModalComponent markup and classes so stock CSS applies.
  const StockModal = ({ show, cancelText, onCancel, accept, children }) =>
    h(
      Modal,
      { className: "ModalComponent vh-clear-fields-modal", keyboard: false, show, onHide: () => {} },
      h(Modal.Header, null, h(Icon, { icon: faExclamationTriangle }), h("span", null, "Clear fields")),
      h(Modal.Body, null, children),
      h(
        Modal.Footer,
        { className: "ModalFooter" },
        h("div"),
        h(
          "div",
          null,
          h(Button, { variant: "secondary", className: "ml-2", onClick: onCancel }, cancelText),
          h(
            Button,
            { variant: accept.variant, className: "ml-2", disabled: accept.disabled, onClick: accept.onClick },
            accept.text
          )
        )
      )
    );

  const ClearFieldsFlow = ({ sceneIds, defaults, sync, onClose }) => {
    const intl = useIntl();
    const Toast = hooks.useToast();
    const [runTask] = GQL.useRunPluginTaskMutation();
    const [updateScene] = GQL.useSceneUpdateMutation();
    const [step, setStep] = useState("pick");
    const [selected, setSelected] = useState(defaults);
    const [busy, setBusy] = useState(false);

    const cancelText = intl.formatMessage({ id: "actions.cancel" });
    const confirmText = intl.formatMessage({ id: "actions.confirm" });
    const summary = `${plural(selected.length, "field")} on ${plural(sceneIds.length, "scene")}`;

    const toggle = (key) =>
      setSelected((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));

    const onConfirm = async () => {
      setBusy(true);
      try {
        if (sync) {
          const input = { id: sceneIds[0] };
          FIELDS.filter((f) => selected.includes(f.key)).forEach((f) => {
            input[f.input] = f.empty();
          });
          await updateScene({ variables: { input } });
          Toast.success(`Cleared ${summary}`);
        } else {
          await runTask({
            variables: {
              plugin_id: PLUGIN_ID,
              task_name: TASK_NAME,
              description: `Clear ${summary}`,
              args_map: { sceneIds, fields: selected },
            },
          });
          Toast.success(`Queued: clearing ${summary}. Refresh the page when the task finishes.`);
        }
        onClose();
      } catch (e) {
        Toast.error(e);
        setBusy(false);
      }
    };

    if (step === "pick") {
      return h(
        StockModal,
        {
          show: true,
          cancelText,
          onCancel: onClose,
          accept: {
            variant: "primary",
            text: "OK",
            disabled: selected.length === 0,
            onClick: () => setStep("confirm"),
          },
        },
        h("p", null, "Select the fields to clear."),
        FIELDS.map((f) =>
          h(Form.Check, {
            key: f.key,
            type: "checkbox",
            id: `vh-clear-fields-${f.key}`,
            label: f.label,
            checked: selected.includes(f.key),
            onChange: () => toggle(f.key),
          })
        )
      );
    }

    return h(
      StockModal,
      {
        show: true,
        cancelText,
        onCancel: () => setStep("pick"),
        accept: { variant: "danger", text: confirmText, disabled: busy, onClick: onConfirm },
      },
      h("p", null, `Clear ${summary}? This removes the following and cannot be undone.`),
      h("ul", null, FIELDS.filter((f) => selected.includes(f.key)).map((f) => h("li", { key: f.key }, f.label)))
    );
  };

  // Scene page tabs are plain React state (no URL), so read the active tab from the DOM.
  const EDIT_TAB_SELECTOR =
    '[data-rb-event-key="scene-edit-panel"].active, [id$="-tabpane-scene-edit-panel"].active';

  const useEditTabActive = (enabled) => {
    const [active, setActive] = useState(false);
    React.useEffect(() => {
      if (!enabled) return undefined;
      const check = () => setActive(!!document.querySelector(EDIT_TAB_SELECTOR));
      check();
      const observer = new MutationObserver(check);
      observer.observe(document.body, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ["class"],
      });
      return () => observer.disconnect();
    }, [enabled]);
    return enabled ? active : true;
  };

  const ClearFieldsButton = ({ sceneIds, sync }) => {
    const { data } = GQL.useConfigurationQuery();
    const [open, setOpen] = useState(false);
    const tabVisible = useEditTabActive(!!sync);

    if (!sceneIds.length) return null;

    const plugins = (data && data.configuration && data.configuration.plugins) || {};
    const pluginSettings = plugins[PLUGIN_ID] || {};
    const defaults = FIELDS.filter((f) => pluginSettings[f.setting] === true).map((f) => f.key);

    return h(
      React.Fragment,
      null,
      tabVisible
        ? h(
            Button,
            { variant: "secondary", className: "vh-clear-fields-button", onClick: () => setOpen(true) },
            "Clear fields…"
          )
        : null,
      open ? h(ClearFieldsFlow, { sceneIds, defaults, sync, onClose: () => setOpen(false) }) : null
    );
  };

  patch.after("SceneList", function (props, _, result) {
    return h(
      React.Fragment,
      null,
      result,
      h(ClearFieldsButton, { sceneIds: Array.from(props.selectedIds || []) })
    );
  });

  patch.after("ScenePage", function (props, _, result) {
    return h(React.Fragment, null, result, h(ClearFieldsButton, { sceneIds: [props.scene.id], sync: true }));
  });
})();
