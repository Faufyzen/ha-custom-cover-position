# Custom Cover Position

🇬🇧 **English** · 🇫🇷 [Français](README.fr.md)

<img src="custom_components/timed_cover/brand/icon.png" alt="Custom Cover Position icon" width="96" align="right">

**Give a position to your shutters, blinds, gates… that do not know where they are.**

Custom Cover Position is a Home Assistant integration that **estimates the state and position of cover entities** from the time they take to open and close, and lets you set up preset positions with a few clicks. It is especially useful for shutters that do not report their position, such as Somfy RTS roller shutters.

It is inspired by two projects: [cover_rf_time_based](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based) by davidramosweb, for estimating the position of a cover entity from the elapsed time, and [ha-cover-time-based](https://github.com/Sese-Schneider/ha-cover-time-based) by Sese-Schneider (MIT license), for a configuration made entirely through the interface, with no YAML file.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Faufyzen&repository=ha-custom-cover-position&category=integration)

**[Why](#why)** · **[Installation](#installation)** · **[Configuration](#configuration)** · **[Entities and names](#entities-and-names)** · **[Resetting the position](#resetting-the-position)** · **[Troubleshooting](#troubleshooting)** · **[Need help or want to report a bug](#need-help-or-want-to-report-a-bug)** · **[Limitations](#limitations)** · **[Languages](#languages-and-documentation)**


## Why

A shutter driven by a radio remote (Somfy RTS, for example) receives commands but **reports nothing back**: Home Assistant does not know whether it is open, closed or somewhere in between. Its state stays "unknown", and you cannot ask it to close or open by "40%".

This integration creates, next to the existing entity (the **source entity**), a **custom cover entity** that:

- **knows its state**: open, closed, opening, closing;
- **calculates its position** (from 0% to 100%) from the time elapsed since the last command;
- **goes to the requested position**: it sends the open or close command, then the stop command at the calculated moment;
- **links itself to the device of the source entity**: no duplicate in your device list, and nothing to create by hand in Helpers or in the configuration.yaml and templates.yaml files;
- **takes over the name and identifier of the source entity**: your scripts and automations keep working without any change;
- **creates preset position buttons** ("Sun shade", "Heat"…) and can **disable the entities of the source device** that would make it lose track of the position.

The position is an **estimate**: it assumes that the shutter always takes the same time to close or open. See [Limitations](#limitations).

## Compatibility

- **Home Assistant 2026.9 or newer.** The integration is tested with version 2026.9.4.
- **Any `cover` entity that can open, close and stop**: roller shutters, blinds, awnings, curtains, gates, garage doors, windows…
- Example: Somfy RTS shutters controlled by Home Assistant through the integration that provides them (Overkiz, for example).

## Installation

<details>
<summary><b>With HACS (recommended)</b></summary>

<br>

This method lets you receive updates directly in HACS.

1. In HACS, click the three dots at the top right, then **Custom repositories**.
2. Paste the repository address: `https://github.com/Faufyzen/ha-custom-cover-position`
3. Choose the type **Integration**, then click **Add**.
4. Search for **Custom Cover Position** in HACS and click **Download**.
5. **Restart Home Assistant**.

</details>

<details>
<summary><b>Without HACS (manual)</b></summary>

<br>

1. Download this repository (green **Code** button, then **Download ZIP**) and unzip it.
2. Copy the `custom_components/timed_cover` folder into the `config/custom_components` folder of your Home Assistant configuration.
3. **Restart Home Assistant.**

</details>

The integration icon only shows after a restart, and your browser may keep the old image in its cache: a hard refresh of the page (⌘⇧R or Ctrl+Shift+R) fixes this.

### Uninstalling

First delete every custom cover entity (Settings → Devices & services → Custom Cover Position → ⋮ menu of the entity → **Delete**): the integration then puts the names, visibility and entities of the source device back as they were. Then remove the integration in HACS (or the `custom_components/timed_cover` folder) and restart Home Assistant.

## Configuration

Everything is set in a configuration window, in two steps.

1. Go to **Settings → Devices & services**.
2. The first time, click **Add integration** and search for **Custom Cover Position**. After that, the integration card appears: its **Add a cover entity** button is enough.

<p align="center">
  <img src="docs/images/add-integration-search.png" alt="The Select brand window with Custom Cover Position found by the search" width="640">
</p>

3. **Step 1: select the source entity**, the one whose position you want to estimate (for example `cover.bedroom_shutter`). It must already exist in Home Assistant.

<table align="center">
  <tr>
    <td><img src="docs/images/step1-choose-source-entity.png" alt="Step 1: Choose the source entity, with the entity selection field" width="320"></td>
    <td><img src="docs/images/step1-entity-list.png" alt="The list of cover entities offered as the source entity" width="320"></td>
  </tr>
</table>

4. **Step 2: fill in the settings** from the table below, then submit.

| Setting | Purpose |
| --- | --- |
| Entity name | The displayed name. The identifier is derived from it: "Bedroom Shutter" gives `cover.bedroom_shutter`. |
| Time to open, Time to close | Duration in seconds of a complete trip (see [Measuring the times](#measuring-the-times)). |
| Send "stop" at the ends | Sends a stop command even after a complete opening or closing. Leave it off unless your shutter does not stop by itself at the end of its travel. |
| Device class | The type of equipment (shutter, blind, venetian blind, awning, curtain, door, gate, garage, damper, window): it determines the icon. |
| Hide the source entity | The source entity disappears from Home Assistant's automatic screens, so that it is not used by mistake. See [Entities and names](#entities-and-names). On by default. |
| Disable the other entities of the source device | Disables everything except the source entity, for example the "My Position" buttons. See [Entities and names](#entities-and-names). Off by default. |
| Preset positions | A list of buttons that bring the shutter to a chosen percentage. See [Preset positions](#preset-positions). |
| Take over the name and identifier of the source entity | The custom cover entity takes the name and identifier of the source entity, which is renamed. See [Entities and names](#entities-and-names). On by default. |
| Suffix for the source entity | Added to the name and identifier of the source entity when it is renamed. "source" by default. |


<table align="center">
  <tr>
    <td><img src="docs/images/step2-settings-top.png" alt="Step 2, top of the form: name, time to open and close, stop at the ends, device class" width="320"></td>
    <td><img src="docs/images/step2-settings-bottom.png" alt="Step 2, bottom of the form: hide the source entity, disable the other entities, preset positions, take over the name, suffix" width="320"></td>
  </tr>
</table>

### Measuring the times

The two times are the only thing the integration cannot guess. Time them with your remote or the original app:

1. **Time to open**: the shutter is closed; start a complete opening and note the time until it stops.
2. **Time to close**: the shutter is open; start a complete closing and note the time.

The two durations are often different (a shutter goes up more slowly than it comes down). To fine-tune later, ask for 50%: if the shutter stops too high or too low, correct the time by a few tenths of a second.

### Preset positions

A preset position is a **button** that brings the shutter to a chosen percentage. The original buttons such as "My Position" (Somfy) command the shutter **without going through the custom cover entity**: it then loses track of its position. The buttons of this integration do go through the custom cover entity, so the position stays right.

In the **Preset positions** block, click **Add**, then give a **name** ("Sun shade"), a **position** from 0 to 100% and, if you like, an **icon**. Each row creates a "<entity name> <position name>" button under the same device, for example "Bedroom Shutter Sun shade". You can create **at most 8 positions**.

<table align="center">
  <tr>
    <td><img src="docs/images/presets-block-empty.png" alt="The Preset positions block, open, with its explanation and the Add button" width="320"></td>
    <td><img src="docs/images/presets-add-dialog.png" alt="The Add window: button name, position in percent and optional icon" width="320"></td>
    <td><img src="docs/images/presets-block-filled.png" alt="The block with two positions, Sun at 60% and Heat at 33%, each with its pencil and trash can" width="320"></td>
  </tr>
</table>

This affects **the favorites in the entity dialog.** When you click an entity, Home Assistant shows position chips under the slider ("0%", "25%", "75%", "100%" by default). With preset positions, the integration replaces them with **0%, your positions, 100%**: a "Heat" button at 33% and a "Sun" button at 60% give 0%, 33%, 60% and 100%, as in the image below. Without any preset position, the default chips stay. If you edit them by hand (⋮ menu → Edit favorites), your choice is kept until the list changes again.

<table align="center">
  <tr>
    <td align="center"><b>Before</b><br><img src="docs/images/source-entity-unknown.png" alt="A shutter entity whose state is Unknown, with only three buttons: up, stop, down" width="320"></td>
    <td align="center"><b>or</b><br><img src="docs/images/entity-favorites-custom.png" alt="The entity dialog afterwards, with its position chips: 0%, 33%, 60% and 100%" width="320"></td>
  </tr>
</table>

Once submitted, a message confirms that the entity was created.

<p align="center">
  <img src="docs/images/success.png" alt="The message Created configuration for Bedroom Shutter with the Finish button" width="320">
</p>

### Changing a setting later

Every setting can still be changed (except the name, the name exchange and the suffix, which can only be chosen at creation): positions to add, edit or delete, times, options. The settings are in **the Custom Cover Position integration**, and **not** in the integration of the source device (Overkiz, for example), even though the custom cover entity is attached to the device of the source entity:

1. **Settings → Devices & services**, **Custom Cover Position** card.
2. Click the **gear** of the entity concerned.
3. Change what you want and submit: the current position is kept.

<p align="center">
  <img src="docs/images/integration-page.png" alt="The Custom Cover Position integration page: the Add a cover entity button, and the Bedroom Shutter entity with its gear" width="640">
</p>

Each preset position has its own pencil and trash can; deleting a row deletes its button.

## Entities and names

### What the integration creates

- **One `cover` entity** (the custom cover entity), with the name and identifier you chose. It exposes the attributes `travel_time_up` and `travel_time_down` (the times, in seconds), `source_entity` (the source entity) and, while moving, `target_position`.
- **One button per preset position.**

It is **unavailable** when the source entity is. The "unknown" state of the source entity, which is normal for shutters that report no state, does not make it unavailable. When Home Assistant restarts, the last position is restored.

### Name exchange

The source entity is often named the way you want to name the custom cover entity (for example `cover.bedroom_shutter`). By default, the integration offers to **take over the name** of the source entity:

- the source entity is renamed with the chosen suffix: "Bedroom Shutter (source)", `cover.bedroom_shutter_source`;
- the custom cover entity takes the name and identifier the source entity had: `cover.bedroom_shutter`.

Your scripts, automations and dashboards that already use `cover.bedroom_shutter` therefore use the custom cover entity, **without any change** on your side. The exchange only happens if you keep the name of the source entity that appears by default in the **Entity name** field when you create the custom cover entity. If you turn the option off, the custom cover entity gets another identifier (`cover.bedroom_shutter_2`) and your scripts will have to be edited to use it.

**When the custom cover entity is deleted, everything is put back**: the source entity gets its name and identifier back. What you changed in the meantime is respected.

### Hiding and disabling

- **Hide the source entity** removes it from the automatically generated screens, so that it is not used by mistake. It is still used internally to send the commands, and it is still offered in the pick lists of scripts (Home Assistant does not allow removing it from them).
- **Disable the other entities of the source device** disables everything except the source entity, for example the "My Position" or "Identify" buttons of a Somfy integration. Careful: the device's **sensors** (battery, power…) are disabled too, which is why the option is off by default. Everything is enabled again if you untick it or delete the custom cover entity.

The device page, before and after: the custom cover entity, its position buttons, the hidden source entity and "My position" disabled.

<table align="center">
  <tr>
    <td align="center"><b>Before</b><br><img src="docs/images/source-device-before.png" alt="The device page before: the shutter entity and the My position button" width="480"></td>
    <td align="center"><b>After</b><br><img src="docs/images/device-page-after.png" alt="The device page after: the custom cover entity, the hidden source entity, the Heat and Sun buttons, and +1 disabled entity" width="480"></td>
  </tr>
</table>

## Resetting the position

The position is estimated: a command given with the original remote, by hand or after a power cut can make it **drift**. There are two ways to put it right:

- **Ask the custom cover entity for a complete opening or closing**: the command is always sent, even if the estimated position is already at the end, and the position is reset to 0% or 100%.
- **Tell it the real position without moving the shutter**: in **Settings → Tools → Actions**, choose the **Set known position** action (Custom Cover Position), select the target (the custom cover entity concerned), enter the real position (between 0 and 100) and click **Perform action**.

<table align="center">
  <tr>
    <td><img src="docs/images/set-known-position-1.png" alt="Steps to reset the position of an entity (1)" width="480"></td>
    <td><img src="docs/images/set-known-position-2.png" alt="Steps to reset the position of an entity (2)" width="480"></td>
  </tr>
</table>

<table align="center">
  <tr>
    <td><img src="docs/images/set-known-position-3.png" alt="Steps to reset the position of an entity (3)" width="480"></td>
    <td><img src="docs/images/set-known-position-4.png" alt="The reset position shown in the control block of the entity" width="480"></td>
  </tr>
</table>

## Troubleshooting

**The position no longer matches reality.** This is normal after a command given outside Home Assistant. See [Resetting the position](#resetting-the-position).

**The shutter stops too high or too low when I ask for a position.** The times need adjusting: correct them by a few tenths of a second in the settings (see [Changing a setting later](#changing-a-setting-later)).

**The custom cover entity is "Unavailable".** The source entity is: the integration that provides it is offline.

**I cannot find the "Add a cover entity" button.** The first time, go through **Add integration** and search for "Custom Cover Position"; the button then exists on the integration page.

**My custom cover entity is called `cover.xxx_2`.** The wanted identifier was already taken, for example by an old entity still listed under Settings → Devices & services → Entities. Delete or rename that entity, then create the custom cover entity again. The same happens to the position buttons if they carry the name of old template buttons.

**I am looking for the settings in the integration of my device (Overkiz…).** They are in Custom Cover Position, not in the integration of the source device. See [Changing a setting later](#changing-a-setting-later).

**The icon does not show.** Restart Home Assistant, then reload the page bypassing the cache.

## Need help or want to report a bug

A problem, a question, an idea? Open a ticket on [GitHub](https://github.com/Faufyzen/ha-custom-cover-position/issues/new/choose). You will help a lot by attaching:

1. **The entity's diagnostics file.** Custom Cover Position integration page, ⋮ menu of the entity, **Download diagnostics**. The file (in English, **with no password or token**) gives the versions of the integration and of Home Assistant, the configuration, the state of the custom cover entity and of the source entity, the position buttons and the other entities of the device. The button on the device page belongs to the integration of the source device and does not give this file.
2. **The debug logs**, if you can: on the integration page, ⋮ menu at the top right, **Enable debug logging**; reproduce the problem; click **Disable debug logging**: a file is downloaded.
3. **A description** of what you expected and what happened, with the steps to reproduce the problem.

Drag the files into the ticket to attach them.

<p align="center">
  <img src="docs/images/diagnostics-menu.png" alt="The ⋮ menu of an entity on the integration page, with Download diagnostics" width="640">
</p>

## Limitations

- **The position is an estimate.** Nothing measures it: it can drift (remote control, wind, motor wear), and it sometimes has to be reset.
- **Response times matter.** With an integration that goes through an online service, the command may arrive with a slight delay. The integration starts its count at the moment the command is accepted.
- **Slat tilt is not supported** (venetian blind or louvered pergola).
- **Only one custom cover entity per source entity.** A source entity that has no unique identifier in Home Assistant can be neither renamed, hidden nor disabled: the name exchange does not happen for it.
- **At most 8 preset positions** per entity.

## Languages and documentation

The integration is translated into **French and English**. It is shown in the language chosen in Home Assistant; for any other language, it is shown in English. A few elements stay in English whatever the language: the diagnostics file, and whatever comes from Home Assistant or from the integration of the source device. This documentation exists in **English** (this file) and in [**French**](README.fr.md). The screenshots are in English.

## License and credits

MIT. Thanks to [davidramosweb](https://github.com/davidramosweb/home-assistant-custom-components-cover-time-based) and to [Sese-Schneider](https://github.com/Sese-Schneider/ha-cover-time-based): their integrations inspired this one.
