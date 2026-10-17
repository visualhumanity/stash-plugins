"use strict";
(() => {
  const { React, patch } = window.PluginApi;

  // TagLink linkType (where the chip is shown) -> tag detail page tab
  const TAB_BY_LINK_TYPE = {
    scene: "scenes",
    image: "images",
    gallery: "galleries",
    group: "groups",
    scene_marker: "markers",
    performer: "performers",
    studio: "studios",
  };

  // TagLink returns an element that carries the computed URL in its `link` prop.
  // Only that prop is replaced; "details" links, unknown link types, tags without
  // an ID and any result that no longer has a `link` prop are left to Stash.
  patch.after("TagLink", function (props, _, result) {
    const tab = TAB_BY_LINK_TYPE[props.linkType || "scene"];
    const id = props.tag && props.tag.id;
    if (!tab || !id || !result || !result.props || typeof result.props.link !== "string") {
      return result;
    }
    return React.cloneElement(result, { link: `/tags/${id}/${tab}` });
  });
})();
