# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class NukeStudioProjectPublishPlugin(HookBaseClass):
    """
    Plugin for publishing a Nuke Studio project.
    """

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """

        # look for icon one level up from this hook's folder in "icons" folder
        return os.path.join(
            self.disk_location,
            os.pardir,
            "icons",
            "publish.png"
        )

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Nuke Studio Project Publisher"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """
        return """
        This plugin will recognize a version number in the file name and will
        publish with that version number to Shotgun.
        """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """
        return {
            "Publish Type": {
                "type": "shotgun_publish_type",
                "default": "Nuke Studio Project",
                "description": "SG publish type to associate publishes with."
            },
        }

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["nukestudio.project"]

    def accept(self, log, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                        all.
            - required: If set to True, the publish task is required and cannot
                        be disabled.
            - enabled:  If True, the publish task will be enabled in the UI by
                        default.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        import hiero.core

        project = item.properties.get("project")

        # ensure there is a document in the item properties
        if not project:
            log.warning("Nuke Studio Project item missing 'project' property.")
            return {"accepted": False}

        engine = self.parent.engine

        # only the active project should be enabled
        enabled = False

        # get the active project. if it can be determined and matches this
        # item's project, then it should be enabled.
        active_project = hiero.ui.activeSequence().project()
        if active_project and active_project.guid() == project.guid():
            enabled = True

        # TODO: this will disable the publish item in the hierarchy.
            # would be good to indicate that the parent shouldn't be enabled.
            # and the parent should also be collapsed

        return {"accepted": True, "required": False, "enabled": enabled}

    def validate(self, log, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity. Use the logger to output further details
        around why validation has failed.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        project = item.properties.get("project")

        if not project.path():
            log.error("Project '%s' has not been saved." % (project.name(),))
            return False

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(os.path.abspath(project.path()))

        publisher = self.parent

        # get the publish name for this file path. this will ensure we get a
        # consistent publish name when looking up existing publishes.
        publish_name = publisher.util.get_publish_name(path)

        log.info("Publish name will be: %s" % (publish_name,))

        # see if there are any other publishes of this path with a status.
        # Note the name, context, and path *must* match the values supplied to
        # register_publish in the publish phase in order for this to return an
        # accurate list of previous publishes of this file.
        publishes = publisher.util.get_conflicting_publishes(
            item.context,
            path,
            publish_name,
            filters=["sg_status_list", "is_not", None]
        )

        if publishes:
            log.warn(
                "Found %s conflicting publishes in Shotgun with the path '%s'. "
                "If you continue, these conflicting publishes will no longer "
                "be available to other users via the loader." %
                (len(publishes), path)
            )

        return True

    def publish(self, log, settings, item):
        """
        Executes the publish logic for the given item and settings. Use the
        logger to give the user status updates.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent

        project = item.properties.get("project")

        # there doesn't appear to be a way to determine if the project has
        # unsaved changes. at least if we're here we have a path. so go ahead
        # and force the save.
        try:
            project.save()
        except Exception, e:
            log.error("Failed to ensure the project '%s' was saved. %s" %
                project.name(), e)
            return

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(os.path.abspath(project.path()))

        # get the publish name for this file path. this will ensure we get a
        # consistent name across version publishes of this file.
        publish_name = publisher.util.get_publish_name(path)

        # extract the version number for publishing. use 1 if no version in path
        version_number = publisher.util.get_version_number(path) or 1

        # arguments for publish registration
        args = {
            "tk": publisher.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": path,
            "name": publish_name,
            "version_number": version_number,
            "thumbnail_path": item.get_thumbnail_as_path(),
            "published_file_type": settings["Publish Type"].value,
        }
        log.debug("Publishing: %s" % (args,))

        # create the publish and stash it in the item properties for other
        # plugins to use.
        item.properties["sg_publish_data"] = sgtk.util.register_publish(**args)

        # now that we've published. keep a handle on the path that was published
        item.properties["path"] = path

    def finalize(self, log, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent

        # get the data for the publish that was just created in SG
        publish_data = item.properties["sg_publish_data"]

        # ensure conflicting publishes have their status cleared
        log.info("Clearing status of conflicting publishes...")
        publisher.util.clear_status_for_conflicting_publishes(
            item.context, publish_data)

        """
        project = item.properties["project"]
        project.saveAs(next_version_path)
        """
