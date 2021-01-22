# -*- coding: utf-8 -*-
"""Timesketch enhancer that exports Timesketch results."""

import time

from dftimewolf.lib import module
from dftimewolf.lib import timesketch_utils
from dftimewolf.lib import utils
from dftimewolf.lib.containers import containers
from dftimewolf.lib.modules import manager as modules_manager


class TimesketchEnhancer(module.BaseModule):
  """Enhance Timesketch results with additional reports.

  Attributes:
    timesketch_api (TimesketchApiClient): Timesketch API client.
  """

  # The name of a ticket attribute that contains the URL to a sketch.
  _SKETCH_ATTRIBUTE_NAME = 'Timesketch URL'

  # Number of seconds the exporter sleeps between checking analyzer status.
  _ANALYZER_SECONDS_BETWEEN_CHECK = 3

  # Maximum number of wait cycles before bailing out waiting for analyzer runs.
  _ANALYZER_MAX_CHECKS = 60
  _ANALYZERS_COMPLETE_SET = frozenset(['ERROR', 'DONE'])

  # Name given to all report containers.
  _REPORT_NAME = 'TimesketchEnhancer'

  def __init__(self, state, name=None, critical=False):
    super(TimesketchEnhancer, self).__init__(
        state, name=name, critical=critical)
    self.timesketch_api = None

    self._aggregations_to_skip = []
    self._formatter = None
    self._include_stories = False
    self._max_checks = self._ANALYZER_MAX_CHECKS
    self._wait_for_analyzers = True
    self._searches_to_skip = []

  def SetUp(self,  # pylint: disable=arguments-differ
            wait_for_analyzers=True,
            searches_to_skip='',
            aggregations_to_skip='',
            include_stories=False,
            token_password='',
            max_checks=0,
            formatter='html'):
    """Sets up a Timesketch Enhancer module.

    Args:
      wait_for_analyzers (bool): If set to True then the enhancer will wait
          until all analyzers are done running. If set to False, the module
          will be skipped, since it does not wait for any results. Defaults to
          True.
      searches_to_skip (str): A comma separated string with a list of names of
          saved searches that are not to be included when generating reports.
      aggregations_to_skip (str): A comma separated string with a list of
          Aggregation names that are not to be included when generating
          reports.
      include_stories (bool): If set to True then story content will be
          dumped into a report, otherwise stories will be ignored. Defaults
          to False.
      token_password (str): optional password used to decrypt the
          Timesketch credential storage. Defaults to an empty string since
          the upstream library expects a string value. An empty string means
          a password will be generated by the upstream library.
      max_checks (int): The enhancer will wait for analyzers to complete before
          attempting to collect data from Timesketch. The tool waits 3 seconds
          before each check, and by default the number of checks is 60, meaning
          that the module will wait at most 180 seconds before continuing. This
          may not be enough time to complete all the work needed, if more time
          is needed max_checks can be increased.
      formatter (str): optional string defining the formatting class that will
          be used for text formatting in reports. Valid options are:
          "html" or "markdown", defaults to "html".
    """
    self.timesketch_api = timesketch_utils.GetApiClient(
        self.state, token_password=token_password)

    if not (self.timesketch_api or self.timesketch_api.session):
      self.ModuleError(
          'Unable to get a Timesketch API client, try deleting the files '
          '~/.timesketchrc and ~/.timesketch.token', critical=True)

    if max_checks:
      self._max_checks = int(max_checks)

    self._include_stories = include_stories
    self._wait_for_analyzers = wait_for_analyzers

    if aggregations_to_skip:
      self._aggregations_to_skip = [
          x.strip() for x in aggregations_to_skip.split(',')]

    if searches_to_skip:
      self._searches_to_skip = [x.strip() for x in searches_to_skip.split(',')]

    if formatter.lower() == 'markdown':
      self._formatter = utils.MarkdownFormatter()
    else:
      self._formatter = utils.HTMLFormatter()

  def _GetSketchURL(self, sketch):
    """Returns a URL to access a sketch."""
    api_root = sketch.api.api_root
    ts_url, _, _ = api_root.partition('/api/v1')
    return '{0:s}/sketch/{1:d}/'.format(ts_url, sketch.id)

  def _GenerateAggregationString(self, aggregations):
    """Returns a string with aggregation data.

    The function runs through all saved aggregations in a sketch
    and returns back a formatted string (using the formatter)
    with the results of the run.

    Args:
      aggregations (list): a list of aggregation objects (Aggregation).

    Returns:
        str: A formatted string with the results of aggregation runs
        on the sketch.
    """
    aggregation_strings = []
    for aggregation in aggregations:
      if aggregation.name in self._aggregations_to_skip:
        continue

      data_frame = aggregation.table
      if data_frame.empty:
        continue

      aggregation_strings.append(self._formatter.IndentText(
          '{0:s}: {1:s}'.format(aggregation.name, aggregation.description),
          level=2))

    return '\n'.join(aggregation_strings)

  def _ProcessAggregations(self, aggregations):
    """Extract and store dataframes from aggregations as containers.

    The function runs through all saved aggregations in a sketch
    and extracts DataFrames from them. The data frames are stored
    as containers, so that other modules can make use of them.

    Args:
      aggregations (list): a list of aggregation objects (Aggregation).
    """
    for aggregation in aggregations:
      if aggregation.name in self._aggregations_to_skip:
        continue

      data_frame = aggregation.table
      if data_frame.empty:
        continue

      data_frame.drop(['bucket_name'], axis=1, inplace=True)
      columns = list(data_frame.columns)

      # We are presenting aggregations here, which is a table that consists of
      # a column name and then the count. For easier reading in reports we want
      # the count to be the last column displayed. In case the aggregation
      # does not have a column named "count" a ValueError will get raised,
      # in those cases we don't want to modify the data frame.
      try:
        count_index = columns.index('count')
        count = columns.pop(count_index)
        columns.append(count)
      except ValueError:
        pass

      self.state.StoreContainer(containers.DataFrame(
          data_frame=data_frame[columns],
          description='Timesketch Aggregation: {0:s}'.format(
              aggregation.name), name=self._REPORT_NAME))

  def _GenerateStoryString(self, stories, sketch_url):
    """Returns a string with story data.

    The function runs through all saved stories in a sketch and returns
    back a formatted string with an overview of all stored stories.

    Args:
      stories (list): a list of Story objects (timesketch_api.story.Story).
      sketch_url (str): the full URL to the sketch.

    Returns:
        str: A formatted string with the results of all stories stored in
        the sketch.
    """
    story_strings = []
    for story in stories:
      story_url = '{0:s}story/{1:d}'.format(sketch_url, story.id)
      story_strings.append(self._formatter.IndentText(
          self._formatter.Link(url=story_url, text=story.title), level=2))

    return '\n'.join(story_strings)

  def _ProcessStories(self, stories):
    """Extracts story content from a list of stories and saves as a report.

    The function runs through all saved stories in a sketch and adds a
    formatted version of the story as a report container.

    Args:
      stories (list): a list of Story objects (timesketch_api.story.Story).
    """
    for story in stories:
      if self._formatter.FORMAT == 'html':
        story_string = story.to_html()
      elif self._formatter.FORMAT == 'markdown':
        story_string = story.to_markdown()
      else:
        story_string = story.to_export_format(self._formatter.FORMAT)

      self.state.StoreContainer(containers.Report(
          module_name='TimesketchEnhancer',
          text_format=self._formatter.FORMAT,
          text=story_string))

  def _GenerateSavedSearchString(self, saved_searches, sketch_url):
    """Returns a string with saved search data.

    The function runs through all saved searches in a sketch and returns
    back a formatted string with the results of the run.

    Args:
      saved_searches (list): a list of Search objects
          (timesketch_api.search.Search).
      sketch_url (str): the full URL to the sketch.

    Returns:
        str: A formatted string with the results of the saved searches in
        the sketch.
    """
    search_strings = []
    for saved_search in saved_searches:
      if saved_search.name in self._searches_to_skip:
        continue

      # We only want to include automatically generated saved searches
      # from analyzers.
      if saved_search.user != 'System':
        continue

      search_url = '{0:s}explore?view={1:d}'.format(
          sketch_url, saved_search.id)
      search_strings.append(self._formatter.IndentText(
          self._formatter.Link(url=search_url, text=saved_search.name),
          level=2))

    return '\n'.join(search_strings)

  def _ProcessSavedSearches(self, saved_searches):
    """Extract events from saved searches and store results as a container.

    The function runs through all saved searches in a sketch and queries
    the datastore for all events that match it and the results as a
    dataframe container to the state object.

    Args:
      saved_searches (list): a list of Search
          objects (timesketch_api.search.Search).
    """
    for saved_search in saved_searches:
      if saved_search.name in self._searches_to_skip:
        continue

      # We only want to include automatically generated searches from
      # analyzers.
      if saved_search.user != 'System':
        continue

      data_frame = saved_search.table
      if data_frame.empty:
        continue

      # Clean up the data frame, remove Timesketch specific columns.
      ts_columns = [x for x in data_frame.columns if x.startswith('_')]
      # Remove all columns from data frame which exist ts_columns list.
      data_frame.drop(ts_columns, axis=1, inplace=True)
      columns = list(data_frame.columns)

      # Move the datetime column to the first column displayed.
      try:
        index = columns.index('datetime')
        datetime = columns.pop(index)
        columns.insert(0, datetime)
      except ValueError:
        pass

      self.state.StoreContainer(
          containers.DataFrame(
              data_frame=data_frame[columns],
              name=self._REPORT_NAME,
              description='Timesketch Saved Search: {0:s} - {1:s}'.format(
                  saved_search.name, saved_search.description)))

  def _WaitForAnalyzers(self, sketch):
    """Wait for all analyzers to complete their run.

    Args:
      sketch (timesketch_api.sketch.Sketch): the sketch object.
    """
    check_number = 0
    while True:
      if check_number >= self._max_checks:
        self.logger.warning(
            'Exceeded maximum checks, not waiting any longer for analyzers '
            'to complete.')
        break

      status_set = set()
      # get_analyzer_status returns a dict with information about the run
      # or all analyzers in a given sketch. One of the information is the
      # current status of the analyzer run, ANALYZER_COMPLETE_SET contains
      # the status values of analyzers that have completed their work.
      for result in sketch.get_analyzer_status():
        status_set.add(result.get('status', 'N/A'))

      if status_set.issubset(self._ANALYZERS_COMPLETE_SET):
        break

      check_number += 1
      time.sleep(self._ANALYZER_SECONDS_BETWEEN_CHECK)

  def Process(self):
    """Executes a Timesketch enhancer module."""
    if not self._wait_for_analyzers:
      self.logger.warning(
          'Not waiting for analyzers to run, skipping enhancer.')
      return

    if not self.timesketch_api:
      message = 'Could not connect to Timesketch server'
      self.ModuleError(message, critical=True)

    sketch = self.state.GetFromCache('timesketch_sketch')
    if not sketch:
      message = (
          'Sketch not found in cache, maybe the previous module was unable '
          'to connect to Timesketch or unable to connect to and/or create '
          'a sketch.')
      self.ModuleError(message, critical=True)

    self.logger.info('Waiting for analyzers to complete their run.')

    summary_lines = [self._formatter.Heading('Timesketch Run', level=1)]
    summary_lines.append(self._formatter.Paragraph(
        'This is a summary of actions taken by Timesketch '
        'during its run.'))
    summary_lines.append(self._formatter.Paragraph(
        'To visit the sketch, click {0:s}'.format(self._formatter.Link(
            url=self._GetSketchURL(sketch), text='here'))))
    summary_lines.append(self._formatter.Paragraph(
        'Here is an overview of actions taken:'))

    self._WaitForAnalyzers(sketch)

    # Force a refresh of sketch data.
    _ = sketch.lazyload_data(refresh_cache=True)

    summary_lines.append(self._formatter.IndentStart())

    saved_searches = sketch.list_saved_searches()
    self._ProcessSavedSearches(saved_searches)
    sketch_url = self._GetSketchURL(sketch)
    search_string = self._GenerateSavedSearchString(
        saved_searches, sketch_url)
    formatted_string = ''
    if search_string:
      formatted_string = self._formatter.IndentText(
          'The following saved searches were discovered:\n'
          '{0:s}{1:s}{2:s}'.format(
              self._formatter.IndentStart(),
              search_string,
              self._formatter.IndentEnd()))
    else:
      formatted_string = self._formatter.IndentText(
          'Analyzers didn\'t save any searches.')
    summary_lines.append(formatted_string)

    aggregations = sketch.list_aggregations(
        exclude_labels=['informational'])
    self._ProcessAggregations(aggregations)
    aggregation_string = self._GenerateAggregationString(aggregations)
    if aggregation_string:
      formatted_string = self._formatter.IndentText(
          'The following aggregations were discovered:'
          '\n{0:s}{1:s}{2:s}'.format(
              self._formatter.IndentStart(),
              aggregation_string,
              self._formatter.IndentEnd()))

    else:
      formatted_string = self._formatter.IndentText(
          'No aggregations were generated by analyzers.')
    summary_lines.append(formatted_string)

    stories = sketch.list_stories()
    if self._include_stories:
      self._ProcessStories(stories)

    story_string = self._GenerateStoryString(stories, sketch_url)
    if story_string:
      formatted_string = self._formatter.IndentText(
          'The following stories were generated:\n{0:s}{1:s}{2:s}'.format(
              self._formatter.IndentStart(),
              story_string,
              self._formatter.IndentEnd()))
    else:
      formatted_string = self._formatter.IndentText(
          'No stories were generated by analyzers.')
    summary_lines.append(formatted_string)

    summary_lines.append(self._formatter.IndentEnd())

    analyzer_results = sketch.get_analyzer_status(as_sessions=True)
    if analyzer_results:
      line_string = self._formatter.Line()
      summary_lines.append(line_string)
      paragraph = self._formatter.Paragraph(
          'Information from analyzer run:')
      summary_lines.append(paragraph)
      indent = self._formatter.IndentStart()
      summary_lines.append(indent)

      completed_ids = set()
      for result in analyzer_results:
        if result.id in completed_ids:
          continue

        if result.log:
          log_text = self._formatter.IndentText(
              'Logs: {0:s}'.format(result.log), level=2)
        else:
          log_text = ''

        formatted_string = self._formatter.IndentText(
            'ID: {0:d}\n{1:s}{2:s}\n{3:s}{4:s}'.format(
                result.id,
                self._formatter.IndentStart(),
                '\n'.join([self._formatter.IndentText(
                    x.strip(), level=2) for x in result.results.split('\n')]),
                log_text,
                self._formatter.IndentEnd()
            )
        )
        summary_lines.append(formatted_string)
        completed_ids.add(result.id)
      summary_lines.append(self._formatter.IndentEnd())

    report_attributes = [{'update_comment': True}]
    self.state.StoreContainer(containers.Report(
        module_name='TimesketchEnhancer', text_format=self._formatter.FORMAT,
        text='\n'.join(summary_lines), attributes=report_attributes))
    self.logger.info('Analyzer reports generated')


modules_manager.ModulesManager.RegisterModule(TimesketchEnhancer)
