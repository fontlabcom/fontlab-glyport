---
this_file: src_docs/md/guides/GLYPH_INFO_MANAGER.md
---

# Glyph Info manager state and lifetime

These selectors implement retained Glyphs source control flow over owned Python
state and explicit lawful primitive providers. They do not install a provider,
load the owner's FontLab session or make private default resources available.
Without a provider (`using_info_provider(...)`, supplied only by tests today)
the lifecycle, debug, queue, sidebar and Chinese/Hangul generation paths
refuse with `UnsupportedCapability`; inside FontLab they are not native
support claims.
The matching Echopy catalogue, authored site guide and ordinary installed tuple
need their own qualification for each delivery.

## Shared graph and raw accessors

`glyphInfos`, `name2Info` and `unicode2Info` return the current raw index
containers. `setGlyphInfos_` stores the supplied object, including `None`, without
copying it. `scriptIDs`, `sidebarCategories`, `categories`, `subCategories` and
`iMatraCombinations` return their exact fields. The all-item, language-group,
category-group and filter-group getter/setter pairs preserve identity and nil.
No setter clears rank caches. `_subcategoriesForSidebarCategory_(None)` returns
nil before requiring an initialized lifecycle; other lookups use the actual
subcategory-order dictionary.

## Lazy ranking

`indexOfObjectInScripts_` enumerates `scriptIDs`.
`indexOfObjectInCategories_` enumerates **sidebarCategories**, then assigns
`Icon`, `SF-Symbol`, `Private Use` and `Corner` successive terminal ranks.
Duplicates overwrite preceding entries. An unknown key returns `2**63 - 1`.
Stored indices use signed 32-bit arithmetic and return as unsigned 64-bit values.

The retained implementation tests for a nil cache before synchronizing the
manager, then builds unconditionally inside that monitor. It publishes the
cache before enumerating and rereads the current field for every insertion.
Lookup locks the captured cache object and reads the then-current cache field.
Python locks/dictionaries qualify owned models; they do not prove Foundation
fast-enumeration mutation detection, key copying or NSNumber/exception ABI.

## Debug and shared construction

`initDebug` configures a fresh queue with the current active processor count,
then replaces the existing **name2Group** dictionary. It does not allocate a
second name index, load glyph data, build sidebar groups or register observers.
A newly allocated owned debug receiver retains nil raw index fields. The actual
base parser adopts its resulting containers on success. Missing files return
false/nil; malformed qualified rows return their actual parse error. Existing
lifecycle/index/local-URL/flags survive reinitialization except for the queue and
group dictionary explicitly replaced by this initializer.

The shared callback preserves an existing local URL and state. Its order is
new queue, current processor count, queue limit, sidebar load, glyph-info load,
queue drain, observer registration. It tests the receiver observer flag's low
bit and writes flag1 only after adding the current global shared receiver.
Failures retain source partial state; there is no invented finally-drain.
Owned NSObject identity initialization does not prove native substitution or
`dispatch_once` ABI and lifetime behavior.

## Placeholder-font cache and observation

`fontForScript_size_` is a **class selector**. Each call resolves its explicit
current provider. The first nil-cache call reads ordered `[script, path]` rows
from `GSScriptToPlaceholderFontPath`, creates and publishes a CF dictionary, then
loads the rows. Each nonnil CGFont is stored in the current global dictionary
and released after the store. Lookup retrieves the current dictionary value;
a nonnil value reaches CTFontCreateWithGraphicsFont with the requested size and
nil matrix/attributes. A nil value returns nil. No arbitrary fallback font or
successful empty resource is invented.

The cache is global and unsynchronized in the retained source. Failed building
keeps completed partial state. Invalidation drops the pointer without releasing
the dictionary. The exact observed key is
`values.GSScriptToPlaceholderFontPath`; unrelated keys do nothing. This behavior
requires individual defaults/CF/CG/CT primitives. Named CF callback tokens are
adapter contracts, not native pointers. CF ownership, native fonts and actual
defaults resources still require a lawful adapter and native qualification.

Explicit `dealloc` removes the current shared observer only when the original
receiver flag equals exactly1, then clears that flag after successful removal.
It always dispatches the explicit `super_dealloc(receiver)` primitive afterward.
Removal failure prevents the flag clear and superclass call. There is no Python
`__del__`, implicit native destruction or blanket state clearing.

## Error presentation and recovery

`reportInfoError` presents GSGlyphsDomain/code1 and the retained English
localized description and recovery suggestion. The owned error is an InfoError
subclass; native NSError identity is unqualified. Presentation return values
are discarded and exceptions propagate.

`attemptRecoveryFromError_optionIndex_` preserves the source's repeated code
reads. Only option1 with first code0x2ae2 or second code0x8702 reads FilePath and
asks the explicit workspace primitive to reveal it. Nil paths remain nil.
Other cases return true. The reveal result is ignored, but a failing reveal
propagates before a successful return. No workspace or native framework is
imported by these source models.
