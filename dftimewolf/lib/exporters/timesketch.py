# -*- coding: utf-8 -*-
"""Export processing results to Timesketch."""

import re

from timesketch_import_client import importer

from dftimewolf.lib import module
from dftimewolf.lib import timesketch_utils
from dftimewolf.lib.containers import containers
from dftimewolf.lib.modules import manager as modules_manager


class TimesketchExporter(module.BaseModule):
  """Exports a given set of plaso or CSV files to Timesketch.

  input: A list of paths to plaso or CSV files.
  output: A URL to the generated timeline.

  Attributes:
    incident_id (str): Incident ID or reference. Used in sketch description.
    sketch_id (int): Sketch ID to add the resulting timeline to. If not
        provided, a new sketch is created.
    timesketch_api (TimesketchApiClient): Timesketch API client.
  """

  # The name of a ticket attribute that contains the URL to a sketch.
  _SKETCH_ATTRIBUTE_NAME = 'Timesketch URL'

  def __init__(self, state):
    super(TimesketchExporter, self).__init__(state)
    self.incident_id = None
    self.sketch_id = None
    self.timesketch_api = None
    self._analyzers = []

  def SetUp(self,  # pylint: disable=arguments-differ
            incident_id=None,
            sketch_id=None,
            analyzers=None):
    """Setup a connection to a Timesketch server and create a sketch if needed.

    Args:
      incident_id (Optional[str]): Incident ID or reference. Used in sketch
          description.
      sketch_id (Optional[int]): Sketch ID to add the resulting timeline to.
          If not provided, a new sketch is created.
      analyzers (Optional[List[str]): If provided a list of analyzer names
          to run on the sketch after they've been imported to Timesketch.
    """
    self.timesketch_api = timesketch_utils.GetApiClient(self.state)
    self.incident_id = None
    self.sketch_id = int(sketch_id) if sketch_id else None
    sketch = None

    # Check that we have a timesketch session.
    if not (self.timesketch_api or self.timesketch_api.session):
      message = 'Could not connect to Timesketch server'
      self.state.AddError(message, critical=True)
      return

    if not self.sketch_id:
      self.sketch_id = self._GetSketchIDFromAttributes()

    if not self.sketch_id:  # No sketch id is provided, create it.
      if incident_id:
        sketch_name = 'Sketch for incident ID: ' + incident_id
      else:
        sketch_name = 'Untitled sketch'
      sketch_description = 'Sketch generated by dfTimewolf'

      sketch = self.timesketch_api.create_sketch(
          sketch_name, sketch_description)
      self.sketch_id = sketch.id
      print('Sketch {0:d} created'.format(self.sketch_id))

    if not sketch:
      sketch = self.timesketch_api.get_sketch(self.sketch_id)

    self.state.AddToCache('timesketch_sketch', sketch)
    if analyzers and isinstance(analyzers, (tuple, list)):
      self._analyzers = analyzers

  def _GetSketchIDFromAttributes(self):
    """Attempts to retrieve a Timesketch ID from ticket attributes.

    Returns:
      int: the sketch idenifier, or None if one was not available.
    """
    attributes = self.state.GetContainers(containers.TicketAttribute)
    for attribute in attributes:
      if attribute.name == self._SKETCH_ATTRIBUTE_NAME:
        sketch_match = re.search(r'sketch/(\d+)/', attribute.value)
        if sketch_match:
          sketch_id = int(sketch_match.group(1), 10)
          return sketch_id
    return None

  def Process(self):
    """Executes a Timesketch export."""
    if not self.timesketch_api:
      message = 'Could not connect to Timesketch server'
      self.state.AddError(message, critical=True)

    sketch = self.state.GetFromCache('timesketch_sketch')
    if not sketch:
      sketch = self.timesketch_api.get_sketch(self.sketch_id)

    recipe_name = self.state.recipe.get('name', 'no_recipe')
    input_names = []
    for description, _ in self.state.input:
      if not description:
        continue
      name = description.rpartition('.')[0]
      name = name.replace(' ', '_').replace('-', '_')
      input_names.append(name)

    if input_names:
      timeline_name = '{0:s}_{1:s}'.format(
          recipe_name, '_'.join(input_names))
    else:
      timeline_name = recipe_name

    with importer.ImportStreamer() as streamer:
      streamer.set_sketch(sketch)
      streamer.set_timeline_name(timeline_name)

      for _, path in self.state.input:
        streamer.add_file(path)

    api_root = sketch.api.api_root
    host_url = api_root.partition('api/v1')[0]
    sketch_url = '{0:s}sketches/{1:d}/'.format(host_url, sketch.id)
    print('Your Timesketch URL is: {0:s}'.format(sketch_url))
    self.state.output = sketch_url

    for analyzer in self._analyzers:
      results = sketch.run_analyzer(
          analyzer_name=analyzer, timeline_name=timeline_name)
      if not results:
        print('Analyzer [{0:s}] not able to run on {1:s}'.format(
            analyzer, timeline_name))
      objects = results.get('objects', [])
      if not objects:
        print(
            'Analyzer [{0:s}] didn\'t provide any session data'.format(
                analyzer))
      print('Analyzer: {0:s} is running, session ID: {1:d}'.format(
          analyzer, objects[0].get('analysis_session', 0)))


modules_manager.ModulesManager.RegisterModule(TimesketchExporter)
