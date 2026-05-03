"""
Asset Allocation Markdown Writer

This module provides functionality to write asset allocation data to markdown files.
It can be used both as part of the main pipeline and as a standalone script.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AllocationWriter:
    """Writes asset allocation data to markdown files."""
    
    def __init__(self, final_data_path: str = "data/final_data.json"):
        """
        Initialize the AllocationWriter.
        
        Args:
            final_data_path: Path to the final_data.json file
        """
        self.final_data_path = Path(final_data_path)
        
    def read_from_final_data(self) -> Optional[Dict[str, Any]]:
        """
        Read allocation data from final_data.json.
        
        Returns:
            Asset allocation data dictionary or None if file not found
        """
        try:
            if not self.final_data_path.exists():
                logger.error(f"Data file not found: {self.final_data_path}")
                return None
                
            with open(self.final_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            allocation_data = data.get("ASSET_ALLOCATION")
            if not allocation_data:
                logger.error("ASSET_ALLOCATION section not found in data")
                return None
                
            return allocation_data
            
        except Exception as e:
            logger.error(f"Error reading allocation data: {str(e)}")
            return None
    
    def write_allocation_table(self, output_path: str = "data/asset_allocation.md") -> bool:
        """
        Write allocation data to a markdown table.
        
        Args:
            output_path: Path where to write the markdown file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            allocation_data = self.read_from_final_data()
            if not allocation_data:
                return False
                
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Generate markdown table
            markdown_content = self._generate_markdown_table(allocation_data)
            
            # Write to file
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
                
            logger.info(f"Allocation table written to: {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing allocation table: {str(e)}")
            return False
    
    def _generate_markdown_table(self, allocation_data: Dict[str, Any]) -> str:
        """
        Generate markdown table content from allocation data.
        
        Args:
            allocation_data: Asset allocation data dictionary
            
        Returns:
            Markdown formatted table string
        """
        net_worth = allocation_data.get("net_worth", 0)
        allocations = allocation_data.get("allocations", {})
        
        # Header with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"# Asset Allocation",
            f"",
            f"Generated on: {timestamp}",
            f"Net Worth: ${net_worth:,.0f}",
            f"",
            f"| Category | Allocation |",
            f"|----------|------------|"
        ]
        
        # Sort allocations by percentage (descending)
        sorted_allocations = sorted(
            allocations.items(), 
            key=lambda x: x[1].get("percentage", 0), 
            reverse=True
        )
        
        # Add allocation rows
        for category, data in sorted_allocations:
            percentage = data.get("percentage", 0)
            # Format percentage to 1 decimal place
            percentage_str = f"{percentage:.1f}%"
            lines.append(f"| {category} | {percentage_str} |")
        
        # Add summary section
        lines.extend([
            f"",
            f"## Summary",
            f"",
            f"Total categories: {len(allocations)}",
            f"Net worth: ${net_worth:,.0f}",
        ])
        
        return "\n".join(lines)
    
    def get_allocation_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get a summary of allocation data.
        
        Returns:
            Summary dictionary or None if data not available
        """
        allocation_data = self.read_from_final_data()
        if not allocation_data:
            return None
            
        net_worth = allocation_data.get("net_worth", 0)
        allocations = allocation_data.get("allocations", {})
        
        # Calculate summary statistics
        total_categories = len(allocations)
        top_category = None
        top_percentage = 0
        
        for category, data in allocations.items():
            percentage = data.get("percentage", 0)
            if percentage > top_percentage:
                top_percentage = percentage
                top_category = category
        
        return {
            "net_worth": net_worth,
            "total_categories": total_categories,
            "top_category": top_category,
            "top_percentage": top_percentage,
            "allocations": allocations
        }


def write_allocation_from_data(data: Dict[str, Any], output_path: str = "data/asset_allocation.md") -> bool:
    """
    Convenience function to write allocation table from existing data dictionary.
    
    Args:
        data: Portfolio data dictionary containing ASSET_ALLOCATION
        output_path: Path where to write the markdown file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        allocation_data = data.get("ASSET_ALLOCATION")
        if not allocation_data:
            logger.error("ASSET_ALLOCATION section not found in provided data")
            return False
            
        writer = AllocationWriter()
        markdown_content = writer._generate_markdown_table(allocation_data)
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
            
        logger.info(f"Allocation table written to: {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing allocation table from data: {str(e)}")
        return False


if __name__ == "__main__":
    """Standalone execution mode."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    logger.info("Running AllocationWriter in standalone mode")
    
    # Create writer and generate table
    writer = AllocationWriter()
    success = writer.write_allocation_table()
    
    if success:
        # Show summary
        summary = writer.get_allocation_summary()
        if summary:
            print(f"\nAllocation Summary:")
            print(f"Net Worth: ${summary['net_worth']:,.0f}")
            print(f"Total Categories: {summary['total_categories']}")
            print(f"Top Category: {summary['top_category']} ({summary['top_percentage']:.1f}%)")
            
            print(f"\nAllocation Breakdown:")
            for category, data in summary['allocations'].items():
                print(f"  {category}: {data['percentage']:.1f}%")
    else:
        print("Failed to generate allocation table")
    
    logger.info("AllocationWriter standalone execution completed")
