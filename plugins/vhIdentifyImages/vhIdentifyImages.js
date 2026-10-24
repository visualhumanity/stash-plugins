"use strict";
(() => {
  const api = window.PluginApi;
  const { React, patch, hooks, libraries } = api;
  const { Form } = libraries.Bootstrap;
  const h = React.createElement;

  const PLUGIN_ID = "vhIdentifyImages";
  // set on the fallback render so this plugin's patch shows the plain settings
  const PLAIN_FLAG = "vhIdentifyImagesPlain";

  // Field options in Identify's order. setting/create mirror FIELD_SETTINGS and the
  // create-missing settings in identify_settings.py and the manifest.
  const FIELDS = [
    { key: "title", setting: "fieldTitle", label: "Title" },
    { key: "code", setting: "fieldCode", label: "Code" },
    { key: "details", setting: "fieldDetails", label: "Details" },
    { key: "date", setting: "fieldDate", label: "Date" },
    { key: "urls", setting: "fieldUrls", label: "URLs" },
    { key: "studio", setting: "fieldStudio", label: "Studio", create: "createMissingStudios" },
    { key: "performers", setting: "fieldPerformers", label: "Performers", create: "createMissingPerformers" },
    { key: "tags", setting: "fieldTags", label: "Tags", create: "createMissingTags" },
  ];

  const STRATEGIES = [
    { value: "ignore", label: "Ignore" },
    { value: "merge", label: "Merge" },
    { value: "overwrite", label: "Overwrite" },
  ];
  const DEFAULT_STRATEGY = "merge";

  // Settings shown above and below the field options, in this order.
  const BEFORE_FIELDS = ["scraperId", "folderPrefixes"];
  const AFTER_FIELDS = [
    "skipSingleNamePerformers",
    "setOrganized",
    "skipOrganized",
    "dryRun",
    "imageLimit",
    "scrapeOnScan",
  ];

  // The value the backend will use: unset or blank means merge, case and spaces are ignored.
  const effectiveStrategy = (value) => {
    if (value === undefined || value === null) return DEFAULT_STRATEGY;
    const normalised = String(value).trim().toLowerCase();
    return normalised === "" ? DEFAULT_STRATEGY : normalised;
  };

  const StrategyRow = ({ field, value, onChange }) => {
    const { Setting } = api.components;
    const current = effectiveStrategy(value);
    const known = STRATEGIES.some((s) => s.value === current);
    const options = STRATEGIES.map((s) => h("option", { key: s.value, value: s.value }, s.label));
    if (!known) {
      // keep a saved value the backend would refuse visible instead of hiding it as merge
      options.push(h("option", { key: "invalid", value: current }, `${value} (invalid)`));
    }
    return h(
      Setting,
      { id: `plugin-${PLUGIN_ID}-${field.setting}`, heading: field.label },
      h(
        Form.Control,
        {
          className: "input-control",
          as: "select",
          value: current,
          onChange: (e) => onChange(e.currentTarget.value),
        },
        options
      )
    );
  };

  // Renders the rest of the PluginSettings patch chain (other plugins' patches, then
  // Stash's own component) for a subset of settings. Calling it from a stable
  // component keeps React from remounting it when the chain hands us a new function
  // on each render.
  //
  // The chain must be called the way Stash calls a component: (props, ctx). Stash
  // appends the next function in the chain as the last argument, so a call with
  // only props would hand the next plugin's patch our function in place of its own.
  //
  // Limitation: Stash counts its way through the chain once per render of the
  // patched component, and this plugin calls the chain twice (above and below the
  // Field options section). With two or more other plugins patching PluginSettings
  // after this one, the second call skips the remaining patches and renders Stash's
  // own component for that block. Nothing is lost; those patches just do not apply
  // to the lower block.
  const StockSettings = ({ render, pluginID, settings }) => render({ pluginID, settings }, undefined);

  // If the custom layout fails (for example because of another plugin's patch),
  // show the plain settings instead of breaking the whole Settings > Plugins page.
  class SettingsBoundary extends React.Component {
    constructor(props) {
      super(props);
      this.state = { failed: false };
    }

    static getDerivedStateFromError() {
      return { failed: true };
    }

    componentDidCatch(error) {
      console.warn(`${PLUGIN_ID}: custom settings layout failed, showing plain settings`, error);
    }

    render() {
      if (!this.state.failed) return this.props.children;
      const { PluginSettings } = api.components;
      const { pluginID, settings } = this.props;
      // a fresh run of the whole patch chain, with this plugin's patch passing through
      return h(PluginSettings, { pluginID, settings, [PLAIN_FLAG]: true });
    }
  }

  const IdentifyImagesSettings = ({ pluginID, settings, original }) => {
    const { SettingGroup, BooleanSetting } = api.components;
    const { plugins, savePluginSettings } = hooks.useSettings();
    const values = plugins[pluginID] || {};
    const save = (key, value) => savePluginSettings(pluginID, { ...values, [key]: value });

    const byName = {};
    settings.forEach((s) => {
      byName[s.name] = s;
    });
    const pick = (names) => names.map((name) => byName[name]).filter(Boolean);
    const placed = new Set(BEFORE_FIELDS.concat(AFTER_FIELDS));
    FIELDS.forEach((f) => {
      placed.add(f.setting);
      if (f.create) placed.add(f.create);
    });
    // anything not placed above still shows, so no setting is ever hidden
    const others = settings.filter((s) => !placed.has(s.name));

    const rows = [];
    FIELDS.forEach((field) => {
      rows.push(
        h(StrategyRow, {
          key: field.setting,
          field,
          value: values[field.setting],
          onChange: (v) => save(field.setting, v),
        })
      );
      if (field.create) {
        rows.push(
          h(BooleanSetting, {
            key: field.create,
            id: `plugin-${PLUGIN_ID}-${field.create}`,
            className: "vh-identify-images-create-missing",
            heading: "Create missing",
            checked: values[field.create] === true,
            onChange: (v) => save(field.create, v),
          })
        );
      }
    });

    return h(
      "div",
      { className: "vh-identify-images-settings" },
      h(StockSettings, { render: original, pluginID, settings: pick(BEFORE_FIELDS) }),
      h(
        SettingGroup,
        {
          settingProps: {
            heading: "Field options",
            subHeading: "As in Identify. Default for every field: Merge. Create missing default: off.",
          },
        },
        rows
      ),
      h(StockSettings, { render: original, pluginID, settings: pick(AFTER_FIELDS).concat(others) })
    );
  };

  patch.instead("PluginSettings", function (props, ctx, original) {
    if (props.pluginID !== PLUGIN_ID || props[PLAIN_FLAG]) {
      return original(props, ctx);
    }
    return h(
      SettingsBoundary,
      { pluginID: props.pluginID, settings: props.settings },
      h(IdentifyImagesSettings, { ...props, original })
    );
  });
})();
