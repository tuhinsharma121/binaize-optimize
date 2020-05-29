from unittest import TestCase

import testing.postgresql

from optimization_platform.src.agents.variation_agent import VariationAgent
from utils.data_store.rds_data_store import RDSDataStore


class TestVariationAgent(TestCase):
    def __init__(self, *args, **kwargs):
        super(TestVariationAgent, self).__init__(*args, **kwargs)
        self.pgsql = testing.postgresql.Postgresql(cache_initialized_db=True)
        self.assertIsNotNone(self.pgsql)
        params = self.pgsql.dsn()
        self.assertEqual('test', params['database'])
        self.assertEqual('127.0.0.1', params['host'])
        self.assertEqual(self.pgsql.settings['port'], params['port'])
        self.assertEqual('postgres', params['user'])
        self.rds_data_store = RDSDataStore(host=params['host'],
                                           port=params['port'],
                                           dbname=params["database"],
                                           user=params["user"],
                                           password=None)

        self.rds_data_store.run_create_table_sql(open("rds_tables.sql", "r").read())

    def test_create_variation_for_client_id_and_experiment_id(self):
        VariationAgent.create_variation_for_client_id_and_experiment_id(data_store=self.rds_data_store,
                                                                        client_id="test_client_id",
                                                                        experiment_id="test_experiment_id",
                                                                        variation_name="test_variation_name",
                                                                        traffic_percentage=100)
        result = self.rds_data_store.run_custom_sql("""
                                                        select 
                                                            client_id, experiment_id, variation_name, 
                                                            traffic_percentage, s3_bucket_name, 
                                                            s3_html_location 
                                                        from variations
                                                    """)
        expected_result = [('test_client_id', 'test_experiment_id', 'test_variation_name', 100, None, None)]
        self.assertListEqual(list1=expected_result, list2=result)

    def test_get_variation_ids_for_client_id_and_experiment_id(self):
        result = VariationAgent.get_variation_ids_for_client_id_and_experiment_id(data_store=self.rds_data_store,
                                                                                  client_id="test_client_id",
                                                                                  experiment_id="test_experiment_id")

        self.assertEqual(first=result, second=None)
        VariationAgent.create_variation_for_client_id_and_experiment_id(data_store=self.rds_data_store,
                                                                        client_id="test_client_id",
                                                                        experiment_id="test_experiment_id",
                                                                        variation_name="test_variation_name_1",
                                                                        traffic_percentage=100)
        VariationAgent.create_variation_for_client_id_and_experiment_id(data_store=self.rds_data_store,
                                                                        client_id="test_client_id",
                                                                        experiment_id="test_experiment_id",
                                                                        variation_name="test_variation_name_2",
                                                                        traffic_percentage=100)
        VariationAgent.create_variation_for_client_id_and_experiment_id(data_store=self.rds_data_store,
                                                                        client_id="test_client_id",
                                                                        experiment_id="test_experiment_id",
                                                                        variation_name="test_variation_name_3",
                                                                        traffic_percentage=100)
        result = VariationAgent.get_variation_ids_for_client_id_and_experiment_id(data_store=self.rds_data_store,
                                                                                  client_id="test_client_id",
                                                                                  experiment_id="test_experiment_id")

        self.assertEqual(first=len(result), second=3)

    def test_get_variation_id_to_recommend(self):
        result = VariationAgent.get_variation_id_to_recommend(data_store=self.rds_data_store,
                                                              client_id="test_client_id",
                                                              experiment_id="test_experiment_id",
                                                              session_id="test_session_id")

        self.assertEqual(first=result, second=None)
        self.rds_data_store.run_insert_into_sql(
            """
            INSERT INTO variations
            values('test_variation_id', 'test_variation_name', 'test_client_id', 'test_experiment_id',
                    80, 's3_bucket_name', 's3_html_location')
            """)
        result = VariationAgent.get_variation_id_to_recommend(data_store=self.rds_data_store,
                                                              client_id="test_client_id",
                                                              experiment_id="test_experiment_id",
                                                              session_id="test_session_id")
        expected_result = {'client_id': 'test_client_id', 'experiment_id': 'test_experiment_id',
                           'variation_id': 'test_variation_id'}
        self.assertDictEqual(d1=result, d2=expected_result)
        self.rds_data_store.run_insert_into_sql(
            """
            INSERT INTO events
            values('served_variation_id' , 'test_client_id', 'test_experiment_id' , 'test_session_id', 'test_event_name', '2020-05-27 09:15:23')
            """)
        result = VariationAgent.get_variation_id_to_recommend(data_store=self.rds_data_store,
                                                              client_id="test_client_id",
                                                              experiment_id="test_experiment_id",
                                                              session_id="test_session_id")

        expected_result = {'client_id': 'test_client_id', 'experiment_id': 'test_experiment_id',
                           'variation_id': 'served_variation_id'}

        self.assertDictEqual(d1=result, d2=expected_result)
