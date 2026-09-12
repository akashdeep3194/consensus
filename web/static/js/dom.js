// DOM primitives. Knows nothing about the game.

export const $ = (id) => document.getElementById(id);

const ENTITIES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape untrusted text before it reaches innerHTML. Handles are player-supplied. */
export const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ENTITIES[c]);

export const on = (node, event, handler) => node.addEventListener(event, handler);

export const show = (node, visible) => { node.hidden = !visible; };

export const setClass = (node, name, present) => node.classList.toggle(name, present);
