"use strict";
(() => {
  const api = window.PluginApi;
  const { React, patch, hooks, libraries } = api;
  const { Form } = libraries.Bootstrap;
  const h = React.createElement;

  const PLUGIN_ID = "vhIdentifyImages";

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

  // Renders Stash's own PluginSettings for a subset of settings. Calling it from a
  // stable component keeps React from remounting it when the patch chain hands us
  // a new function on each render.
  const StockSettings = ({ render, pluginID, settings }) => render({ pluginID, settings });

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
    if (props.pluginID !== PLUGIN_ID) {
      return original(props, ctx);
    }
    return h(IdentifyImagesSettings, { ...props, original });
  });
})();
