#!/usr/bin/env python3
"""
Oracle to PostgreSQL 17 Schema Converter
Converts Oracle SQL schema file to PostgreSQL 17 compatible format
"""

import re
import sys
from collections import defaultdict

class OracleToPostgreSQLConverter:
    def __init__(self):
        self.stats = defaultdict(int)
        self.in_create_block = False
        self.create_block_lines = []
        self.create_block_type = None

    def convert_data_types(self, line):
        """Convert Oracle data types to PostgreSQL equivalents"""
        # NUMBER conversions
        line = re.sub(r'\bNUMBER\s*\(\s*(\d+)\s*,\s*0\s*\)', r'INTEGER', line, flags=re.IGNORECASE)
        line = re.sub(r'\bNUMBER\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', r'NUMERIC(\1,\2)', line, flags=re.IGNORECASE)
        line = re.sub(r'\bNUMBER\s*\(\s*(\d+)\s*\)', r'NUMERIC(\1)', line, flags=re.IGNORECASE)
        line = re.sub(r'\bNUMBER\b(?!\s*\()', r'NUMERIC', line, flags=re.IGNORECASE)

        # String types
        line = re.sub(r'\bVARCHAR2\b', 'VARCHAR', line, flags=re.IGNORECASE)
        line = re.sub(r'\bNVARCHAR2\b', 'VARCHAR', line, flags=re.IGNORECASE)

        # LOB types
        line = re.sub(r'\bCLOB\b', 'TEXT', line, flags=re.IGNORECASE)
        line = re.sub(r'\bNCLOB\b', 'TEXT', line, flags=re.IGNORECASE)
        line = re.sub(r'\bBLOB\b', 'BYTEA', line, flags=re.IGNORECASE)
        line = re.sub(r'\bLONG\b(?!\s+RAW)', 'TEXT', line, flags=re.IGNORECASE)

        # RAW types
        line = re.sub(r'\bRAW\s*\(', 'BYTEA', line, flags=re.IGNORECASE)
        line = re.sub(r'\bLONG\s+RAW\b', 'BYTEA', line, flags=re.IGNORECASE)

        # DATE type (Oracle DATE includes time, so use TIMESTAMP)
        line = re.sub(r'\bDATE\b', 'TIMESTAMP', line, flags=re.IGNORECASE)

        return line

    def convert_functions(self, line):
        """Convert Oracle functions to PostgreSQL equivalents"""
        # SYSDATE -> CURRENT_TIMESTAMP
        line = re.sub(r'\bSYSDATE\b', 'CURRENT_TIMESTAMP', line, flags=re.IGNORECASE)

        # NVL -> COALESCE
        line = re.sub(r'\bNVL\s*\(', 'COALESCE(', line, flags=re.IGNORECASE)

        # NVL2(expr1, expr2, expr3) -> CASE WHEN expr1 IS NOT NULL THEN expr2 ELSE expr3 END
        # This is complex, so we'll do a simple replacement for now
        def nvl2_replace(match):
            return 'CASE WHEN ' + match.group(1) + ' IS NOT NULL THEN ' + match.group(2) + ' ELSE ' + match.group(3) + ' END'

        # Note: This is a simplified NVL2 conversion - complex nested cases may need manual review
        # line = re.sub(r'NVL2\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\s*\)', nvl2_replace, line, flags=re.IGNORECASE)

        # DECODE - this is complex, keep as is for now (will be in comments)
        # PostgreSQL equivalent is CASE WHEN...

        # TRUNC(date) -> DATE_TRUNC('day', date)
        line = re.sub(r'\bTRUNC\s*\(\s*([^,)]+)\s*\)', r"DATE_TRUNC('day', \1)", line, flags=re.IGNORECASE)

        # INSTR -> POSITION
        line = re.sub(r'\bINSTR\s*\(\s*([^,]+)\s*,\s*([^)]+)\s*\)', r'POSITION(\2 IN \1)', line, flags=re.IGNORECASE)

        # SUBSTR -> SUBSTRING
        line = re.sub(r'\bSUBSTR\s*\(', 'SUBSTRING(', line, flags=re.IGNORECASE)

        # LENGTH is the same in both
        # CHR is the same in both

        return line

    def remove_schema_qualification(self, line):
        """Remove ARGUS_APP schema qualification"""
        line = re.sub(r'"ARGUS_APP"\.', '', line)
        line = re.sub(r'\bARGUS_APP\.', '', line, flags=re.IGNORECASE)
        return line

    def convert_drop_statement(self, line):
        """Convert DROP statements to include IF EXISTS"""
        # DROP VIEW
        if re.match(r'^\s*DROP\s+VIEW\s+', line, re.IGNORECASE):
            self.stats['drop_views'] += 1
            line = re.sub(r'(DROP\s+VIEW\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)
            line = re.sub(r';$', ' CASCADE;', line.rstrip())

        # DROP TABLE
        elif re.match(r'^\s*DROP\s+TABLE\s+', line, re.IGNORECASE):
            self.stats['drop_tables'] += 1
            line = re.sub(r'(DROP\s+TABLE\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)
            line = re.sub(r'\s+cascade\s+constraints\s*;', ' CASCADE;', line, flags=re.IGNORECASE)

        # DROP SEQUENCE
        elif re.match(r'^\s*DROP\s+SEQUENCE\s+', line, re.IGNORECASE):
            self.stats['drop_sequences'] += 1
            line = re.sub(r'(DROP\s+SEQUENCE\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)
            if not line.rstrip().endswith(';'):
                line = line.rstrip() + ';\n'

        # DROP TYPE
        elif re.match(r'^\s*DROP\s+TYPE\s+', line, re.IGNORECASE):
            self.stats['drop_types'] += 1
            line = re.sub(r'(DROP\s+TYPE\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)
            line = re.sub(r';$', ' CASCADE;', line.rstrip())

        # DROP PACKAGE (PostgreSQL doesn't have packages, comment out)
        elif re.match(r'^\s*DROP\s+PACKAGE\s+', line, re.IGNORECASE):
            self.stats['drop_packages'] += 1
            line = '-- ' + line + ' -- Oracle package, convert to PostgreSQL schema/functions\n'

        # DROP FUNCTION
        elif re.match(r'^\s*DROP\s+FUNCTION\s+', line, re.IGNORECASE):
            self.stats['drop_functions'] += 1
            line = re.sub(r'(DROP\s+FUNCTION\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)
            line = re.sub(r';$', ' CASCADE;', line.rstrip())

        # DROP PROCEDURE
        elif re.match(r'^\s*DROP\s+PROCEDURE\s+', line, re.IGNORECASE):
            self.stats['drop_procedures'] += 1
            line = re.sub(r'(DROP\s+PROCEDURE\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)
            line = re.sub(r';$', ' CASCADE;', line.rstrip())

        # DROP TRIGGER
        elif re.match(r'^\s*DROP\s+TRIGGER\s+', line, re.IGNORECASE):
            self.stats['drop_triggers'] += 1
            line = re.sub(r'(DROP\s+TRIGGER\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)

        # DROP INDEX
        elif re.match(r'^\s*DROP\s+INDEX\s+', line, re.IGNORECASE):
            self.stats['drop_indexes'] += 1
            line = re.sub(r'(DROP\s+INDEX\s+)', r'\1IF EXISTS ', line, flags=re.IGNORECASE)

        return line

    def convert_create_view(self, line):
        """Convert CREATE VIEW statements"""
        # Remove FORCE EDITIONABLE keywords (Oracle-specific)
        line = re.sub(r'\bFORCE\s+EDITIONABLE\s+', '', line, flags=re.IGNORECASE)
        line = re.sub(r'\bFORCE\s+', '', line, flags=re.IGNORECASE)
        line = re.sub(r'\bEDITIONABLE\s+', '', line, flags=re.IGNORECASE)

        if 'CREATE' in line.upper() and 'VIEW' in line.upper():
            self.stats['create_views'] += 1

        return line

    def convert_create_table(self, line):
        """Convert CREATE TABLE statements"""
        if 'CREATE' in line.upper() and 'TABLE' in line.upper():
            self.stats['create_tables'] += 1
            # Remove EDITIONABLE keyword
            line = re.sub(r'\bEDITIONABLE\s+', '', line, flags=re.IGNORECASE)

        return line

    def convert_create_sequence(self, line):
        """Convert CREATE SEQUENCE statements"""
        if 'CREATE' in line.upper() and 'SEQUENCE' in line.upper():
            self.stats['create_sequences'] += 1

        # Oracle: INCREMENT BY, START WITH, MAXVALUE, MINVALUE, CACHE
        # PostgreSQL supports these same keywords

        return line

    def convert_create_index(self, line):
        """Convert CREATE INDEX statements"""
        if 'CREATE' in line.upper() and 'INDEX' in line.upper():
            self.stats['create_indexes'] += 1

        return line

    def convert_grant_statement(self, line):
        """Convert GRANT statements"""
        if re.match(r'^\s*GRANT\s+', line, re.IGNORECASE):
            self.stats['grants'] += 1
            # Keep GRANT statements but remove schema qualification

        return line

    def convert_constraint(self, line):
        """Convert constraint definitions"""
        # PostgreSQL supports most Oracle constraint syntax
        # Just need to handle data types within constraints

        return line

    def convert_line(self, line):
        """Main conversion function for a single line"""
        original_line = line

        # Skip empty lines and pure comment lines
        if not line.strip() or line.strip().startswith('--'):
            return line

        # Handle DROP statements
        if re.match(r'^\s*DROP\s+', line, re.IGNORECASE):
            line = self.convert_drop_statement(line)

        # Handle CREATE VIEW
        if 'CREATE' in line.upper() and 'VIEW' in line.upper():
            line = self.convert_create_view(line)

        # Handle CREATE TABLE
        if 'CREATE' in line.upper() and 'TABLE' in line.upper():
            line = self.convert_create_table(line)

        # Handle CREATE SEQUENCE
        if 'CREATE' in line.upper() and 'SEQUENCE' in line.upper():
            line = self.convert_create_sequence(line)

        # Handle CREATE INDEX
        if 'CREATE' in line.upper() and 'INDEX' in line.upper():
            line = self.convert_create_index(line)

        # Handle GRANT statements
        if re.match(r'^\s*GRANT\s+', line, re.IGNORECASE):
            line = self.convert_grant_statement(line)

        # Remove schema qualification
        line = self.remove_schema_qualification(line)

        # Convert data types
        line = self.convert_data_types(line)

        # Convert functions
        line = self.convert_functions(line)

        # Handle V$PARAMETER (Oracle system view) - convert to comment
        if 'V$PARAMETER' in line.upper():
            line = '-- ' + line + ' -- Oracle system view, needs manual conversion\n'

        # Handle DUAL table references
        line = re.sub(r'\bFROM\s+DUAL\b', 'FROM (SELECT 1) AS dual', line, flags=re.IGNORECASE)

        # Handle GREATEST/LEAST functions (supported in PostgreSQL)
        # No change needed

        return line

    def convert_file(self, input_file, output_file):
        """Convert entire Oracle SQL file to PostgreSQL format"""
        print(f"Converting {input_file} to {output_file}...")
        print("This may take a while for large files...")

        line_count = 0

        with open(input_file, 'r', encoding='utf-8', errors='ignore') as inf, \
             open(output_file, 'w', encoding='utf-8') as outf:

            # Write header
            outf.write("-- PostgreSQL 17 Schema\n")
            outf.write("-- Converted from Oracle format\n")
            outf.write("-- Conversion date: " + str(__import__('datetime').datetime.now()) + "\n")
            outf.write("--\n")
            outf.write("-- IMPORTANT: This is an automated conversion.\n")
            outf.write("-- Please review the following:\n")
            outf.write("-- 1. NVL2 functions may need manual conversion to CASE statements\n")
            outf.write("-- 2. DECODE functions need conversion to CASE statements\n")
            outf.write("-- 3. Oracle packages need to be converted to PostgreSQL schemas/functions\n")
            outf.write("-- 4. PL/SQL procedures/functions need conversion to PL/pgSQL\n")
            outf.write("-- 5. Triggers need syntax adjustments\n")
            outf.write("-- 6. Some Oracle-specific features may need alternative approaches\n")
            outf.write("--\n\n")

            for line in inf:
                line_count += 1

                if line_count % 10000 == 0:
                    print(f"  Processed {line_count} lines...")

                converted_line = self.convert_line(line)
                outf.write(converted_line)

        print(f"\nConversion complete! Processed {line_count} lines.")
        print("\nConversion Statistics:")
        print("=" * 60)
        print(f"DROP Views:      {self.stats['drop_views']}")
        print(f"DROP Tables:     {self.stats['drop_tables']}")
        print(f"DROP Sequences:  {self.stats['drop_sequences']}")
        print(f"DROP Types:      {self.stats['drop_types']}")
        print(f"DROP Packages:   {self.stats['drop_packages']} (commented out)")
        print(f"DROP Functions:  {self.stats['drop_functions']}")
        print(f"DROP Procedures: {self.stats['drop_procedures']}")
        print(f"DROP Triggers:   {self.stats['drop_triggers']}")
        print(f"DROP Indexes:    {self.stats['drop_indexes']}")
        print(f"CREATE Views:    {self.stats['create_views']}")
        print(f"CREATE Tables:   {self.stats['create_tables']}")
        print(f"CREATE Sequences: {self.stats['create_sequences']}")
        print(f"CREATE Indexes:  {self.stats['create_indexes']}")
        print(f"GRANT Statements: {self.stats['grants']}")
        print("=" * 60)

        return self.stats

def main():
    input_file = '/home/user/ich_ora2pg/argus_app_schema.sql'
    output_file = '/home/user/ich_ora2pg/argus_app_schema_postgresql.sql'

    converter = OracleToPostgreSQLConverter()
    stats = converter.convert_file(input_file, output_file)

    print(f"\nOutput written to: {output_file}")
    print("\nIMPORTANT NOTES:")
    print("1. Review and test the converted schema before deployment")
    print("2. Some Oracle-specific constructs have been commented out")
    print("3. Complex NVL2 and DECODE functions may need manual conversion")
    print("4. Oracle packages need to be redesigned as PostgreSQL schemas with functions")
    print("5. PL/SQL code blocks need conversion to PL/pgSQL")
    print("6. Test all triggers, functions, and procedures thoroughly")

if __name__ == '__main__':
    main()
