#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests the Timesketch exporter."""

import unittest

import mock

from dftimewolf import config
from dftimewolf.lib import state
from dftimewolf.lib.exporters import timesketch


class TimesketchExporterTest(unittest.TestCase):
  """Tests for the Timesketch exporter."""

  def testInitialization(self):
    """Tests that the processor can be initialized."""
    test_state = state.DFTimewolfState(config.Config)
    timesketch_exporter = timesketch.TimesketchExporter(test_state)
    self.assertIsNotNone(timesketch_exporter)

  # pylint: disable=invalid-name
  @mock.patch('dftimewolf.lib.timesketch_utils.GetApiClient')
  def testSetup(self, mock_GetApiClient):
    """Tests the SetUp function."""
    mock_sketch = mock.Mock()
    mock_sketch.id = 1234
    mock_api_client = mock.Mock()
    mock_api_client.create_sketch.return_value = mock_sketch
    mock_GetApiClient.return_value = mock_api_client
    test_state = state.DFTimewolfState(config.Config)
    timesketch_exporter = timesketch.TimesketchExporter(test_state)
    timesketch_exporter.SetUp(
        incident_id=None,
        sketch_id=None,
        analyzers=None
    )
    self.assertEqual(timesketch_exporter.sketch_id, 1234)
    mock_api_client.create_sketch.assert_called_with(
        'Untitled sketch', 'Sketch generated by dfTimewolf')

  # pylint: disable=invalid-name
  @mock.patch('dftimewolf.lib.timesketch_utils.GetApiClient')
  def testSetupForceIncidentId(self, mock_GetApiClient):
    """Tests the SetUp function when an incident ID is passed."""
    mock_sketch = mock.Mock()
    mock_sketch.id = 1234
    mock_api_client = mock.Mock()
    mock_api_client.create_sketch.return_value = mock_sketch
    mock_GetApiClient.return_value = mock_api_client
    test_state = state.DFTimewolfState(config.Config)
    timesketch_exporter = timesketch.TimesketchExporter(test_state)
    timesketch_exporter.SetUp(
        incident_id='9999',
        sketch_id=None,
        analyzers=None
    )
    self.assertEqual(timesketch_exporter.sketch_id, 1234)
    mock_api_client.create_sketch.assert_called_with(
        'Sketch for incident ID: 9999', 'Sketch generated by dfTimewolf')

  # pylint: disable=invalid-name
  @mock.patch('dftimewolf.lib.timesketch_utils.GetApiClient')
  def testSetupForceSketchId(self, mock_GetApiClient):
    """Tests the SetUp function when an incident ID is passed."""
    mock_sketch = mock.Mock()
    mock_api_client = mock.Mock()
    mock_api_client.get_sketch.return_value = mock_sketch
    mock_GetApiClient.return_value = mock_api_client
    test_state = state.DFTimewolfState(config.Config)
    timesketch_exporter = timesketch.TimesketchExporter(test_state)
    timesketch_exporter.SetUp(
        incident_id='9999',
        sketch_id='6666',
        analyzers=None
    )
    self.assertEqual(timesketch_exporter.sketch_id, 6666)
    mock_api_client.get_sketch.assert_called_with(6666)


if __name__ == '__main__':
  unittest.main()
